"""Online subscription keys. Persist only a digest; never put keys in URLs/logs."""
import base64
import hashlib
import json
import secrets
from urllib.parse import urlsplit
from django import forms
from django.conf import settings
from django.contrib.auth import login,logout
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render,redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import Workspace,Subscription,AuditEvent
from .security import consume_limit


def canonical_origin(value):
    if not isinstance(value,str) or len(value)>500:raise ValueError('Enter a valid server origin.')
    url=urlsplit(value)
    url.port  # Validate the optional port before issuing or accepting a key.
    if url.username or url.password or url.query or url.fragment or url.path not in ('','/') or not url.hostname:
        raise ValueError('Configure APP_PUBLIC_URL with the server origin only.')
    if url.scheme!='https' and not (url.scheme=='http' and url.hostname in ('localhost','127.0.0.1','::1')):
        raise ValueError('Subscription keys require HTTPS, or same-PC loopback HTTP.')
    return f'{url.scheme}://{url.netloc}'


def decode_key(value):
    if not isinstance(value,str) or len(value)>2000 or not value.startswith('SB1.'):
        raise ValueError('Enter the subscription key supplied by your administrator.')
    encoded=value[4:]
    try:
        packet=json.loads(base64.b64decode(encoded+'='*((-len(encoded))%4),altchars=b'-_',validate=True))
        if not isinstance(packet,dict) or set(packet)!= {'origin','token'}:raise ValueError()
        origin=canonical_origin(packet['origin']);token=packet['token']
        if not isinstance(token,str) or len(token)!=43 or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_' for c in token):raise ValueError()
    except (ValueError,TypeError,KeyError,UnicodeDecodeError):
        raise ValueError('Enter a valid subscription key.') from None
    return origin,hashlib.sha256(token.encode()).hexdigest()


@transaction.atomic
def issue_key(subscription,operator):
    if not operator.is_active or not operator.is_superuser:raise PermissionError('Only product administrators may issue subscription keys.')
    origin=canonical_origin(settings.APP_PUBLIC_URL)
    Workspace.objects.select_for_update().get(pk=subscription.workspace_id)
    subscription=Subscription.objects.select_for_update().get(pk=subscription.pk)
    if subscription.workspace.owner.is_superuser:raise ValueError('Subscription keys can only be issued for customer accounts.')
    if subscription.status not in ('active','trial') or subscription.expires_on<timezone.localdate():raise ValueError('Set an active subscription and future expiry before issuing a key.')
    token=secrets.token_urlsafe(32)
    subscription.key_digest=hashlib.sha256(token.encode()).hexdigest()
    subscription.key_enabled=True;subscription.requires_activation=True;subscription.key_version+=1;subscription.activated_at=None
    subscription.save(update_fields=['key_digest','key_enabled','requires_activation','key_version','activated_at'])
    AuditEvent.objects.create(workspace=subscription.workspace,actor=operator,action='provider.key_issued',details={'version':subscription.key_version,'expires_on':str(subscription.expires_on)})
    packet=json.dumps({'origin':origin,'token':token},separators=(',',':')).encode()
    return 'SB1.'+base64.urlsafe_b64encode(packet).decode().rstrip('=')


def activate(request,value):
    if isinstance(value,str):value=value.strip()
    origin,digest=decode_key(value)
    if origin!=canonical_origin(settings.APP_PUBLIC_URL):raise ValueError('This key belongs to a different accounting server.')
    if not consume_limit('activation-ip',request.META.get('REMOTE_ADDR',''),30):raise ValueError('Too many activation attempts. Wait 15 minutes before trying again.')
    subscription=Subscription.objects.filter(key_digest=digest).first()
    if not subscription:raise ValueError('Invalid subscription key. Contact your administrator.')
    with transaction.atomic():
        workspace=Workspace.objects.select_for_update().select_related('owner').get(pk=subscription.workspace_id)
        subscription=Subscription.objects.select_for_update().get(pk=subscription.pk)
        today=timezone.localdate()
        if subscription.key_digest!=digest or not subscription.key_enabled or subscription.status not in ('active','trial') or not subscription.starts_on<=today<=subscription.expires_on or not workspace.owner.is_active or workspace.owner.is_superuser:
            raise ValueError('This subscription is inactive, not yet started or expired. Contact your administrator.')
        if subscription.activated_at is None:
            subscription.activated_at=timezone.now();subscription.save(update_fields=['activated_at'])
        AuditEvent.objects.create(workspace=workspace,actor=workspace.owner,action='subscription.activated',details={'version':subscription.key_version})
        version=subscription.key_version
    login(request,workspace.owner,backend='django.contrib.auth.backends.ModelBackend')
    request.session['subscription_key_version']=version
    return subscription


class ActivationForm(forms.Form):
    key=forms.CharField(label='Subscription key',max_length=2000,widget=forms.Textarea(attrs={'rows':4,'autocomplete':'off','spellcheck':'false'}))


def activation_page(request):
    form=ActivationForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        try:activate(request,form.cleaned_data['key'].strip())
        except ValueError as error:form.add_error('key',str(error))
        else:return redirect('/')
    return render(request,'books/activate.html',{'form':form})


@require_POST
def activation_api(request):
    try:
        payload=json.loads(request.body)
        subscription=activate(request,payload.get('key') if isinstance(payload,dict) else None)
    except (ValueError,TypeError,UnicodeDecodeError) as error:
        return JsonResponse({'error':str(error) or 'Invalid activation request.'},status=400)
    return JsonResponse({'activated':True,'expires_on':subscription.expires_on.isoformat()})
