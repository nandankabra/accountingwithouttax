"""Offline Ed25519 licences. The issuer's private key is never packaged."""
import base64
import json
import os
import uuid
from datetime import date
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from .models import OfflineLicense, Workspace, AuditEvent
from .services import create_workspace


def signing_key_path():
    return Path(os.getenv('SIMPLEBOOKS_SIGNING_KEY', settings.BASE_DIR / '.runtime/offline-signing.pem'))


def initialize_signer():
    path = signing_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        key = Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        try:
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as handle:
                handle.write(key)
        except FileExistsError:
            pass
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('Configure an Ed25519 provider signing key.')
    return key


def public_key_bytes():
    return initialize_signer().public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


def b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def unb64(value):
    return base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)


@transaction.atomic
def issue_offline_key(subscription, operator, installation_id):
    if not operator.is_active or not operator.is_superuser:
        raise PermissionError('Only product administrators may issue licences.')
    installation_id = str(uuid.UUID(str(installation_id)))
    workspace = Workspace.objects.select_for_update().get(pk=subscription.workspace_id)
    subscription.refresh_from_db()
    if workspace.owner.is_superuser or subscription.status not in ('active', 'trial') or subscription.expires_on < timezone.localdate():
        raise ValueError('Set an active customer subscription with a future expiry first.')
    packet = {'v': 2, 'installation': installation_id, 'customer': str(workspace.pk), 'company': workspace.name,
              'email': workspace.owner.email or workspace.owner.username,
              'starts': str(subscription.starts_on), 'expires': str(subscription.expires_on),
              'issued': timezone.now().isoformat()}
    payload = json.dumps(packet, sort_keys=True, separators=(',', ':')).encode()
    signature = initialize_signer().sign(payload)
    AuditEvent.objects.create(workspace=workspace, actor=operator, action='provider.offline_key_issued', details={'installation': installation_id, 'expires_on': packet['expires']})
    return 'SB2.' + b64(payload) + '.' + b64(signature)


def verify_key(value, installation_id=None, *, bind_installation=True):
    try:
        if not isinstance(value, str) or len(value) > 4000:
            raise ValueError()
        prefix, body, signature = value.strip().split('.')
        if prefix != 'SB2':
            raise ValueError()
        payload = unb64(body)
        public = serialization.load_pem_public_key(Path(settings.OFFLINE_PUBLIC_KEY).read_bytes())
        if not isinstance(public, Ed25519PublicKey):
            raise ValueError()
        public.verify(unb64(signature), payload)
        packet = json.loads(payload)
        if set(packet) != {'v', 'installation', 'customer', 'company', 'email', 'starts', 'expires', 'issued'} or packet['v'] != 2:
            raise ValueError()
        uuid.UUID(packet['customer'])
        if bind_installation and str(uuid.UUID(packet['installation'])) != (installation_id or settings.INSTALLATION_ID):
            raise ValueError('This key belongs to another installation. Ask your provider for a key for this PC.')
        start, end = date.fromisoformat(packet['starts']), date.fromisoformat(packet['expires'])
        if end < start or not isinstance(packet['company'], str) or not 1 <= len(packet['company']) <= 160 or not isinstance(packet['email'], str) or len(packet['email']) > 150:
            raise ValueError()
        from datetime import datetime
        issued = datetime.fromisoformat(packet['issued'])
        if issued.tzinfo is None:
            raise ValueError()
        return packet
    except (ValueError, TypeError, KeyError, InvalidSignature, UnicodeError) as error:
        if str(error).startswith('This key belongs'):
            raise
        raise ValueError('Invalid offline subscription key. Contact your provider.') from None


def licence_access(workspace):
    state = OfflineLicense.objects.filter(workspace=workspace).first()
    if not state:
        return False, False
    try:
        packet = verify_key(state.signed_key)
        if packet['customer'] != str(workspace.pk):
            return False, False
        today = timezone.localdate()
        previous = state.last_seen_date
        if today > previous:
            OfflineLicense.objects.filter(pk=state.pk, last_seen_date__lt=today).update(last_seen_date=today)
        allowed = previous <= today and date.fromisoformat(packet['starts']) <= today <= date.fromisoformat(packet['expires'])
        return True, allowed
    except ValueError:
        return False, False


@transaction.atomic
def activate_offline(request, value):
    packet = verify_key(value)
    today = timezone.localdate()
    start, end = date.fromisoformat(packet['starts']), date.fromisoformat(packet['expires'])
    if not start <= today <= end:
        raise ValueError('This subscription is not yet active or has expired. Ask your provider for a renewal key.')
    existing = OfflineLicense.objects.select_for_update().select_related('workspace__owner').first()
    if existing:
        if str(existing.workspace_id) != packet['customer']:
            raise ValueError('This data file belongs to a different company. Restore its backup or contact your provider.')
        if existing.last_seen_date > today:
            raise ValueError('The PC date has moved backwards. Correct its date before activating.')
        old = verify_key(existing.signed_key, bind_installation=False)
        from datetime import datetime
        if datetime.fromisoformat(packet['issued']) < datetime.fromisoformat(old['issued']):
            raise ValueError('A newer licence is already installed. Use the latest renewal key.')
        workspace = existing.workspace
    else:
        if Workspace.objects.exists():
            raise ValueError('Existing company data requires a matching offline licence migration.')
        user = User.objects.create(username='local-owner', email=packet['email'])
        user.set_unusable_password()
        user.save(update_fields=['password'])
        workspace = create_workspace(user, packet['company'], workspace_id=packet['customer'])
    subscription = workspace.subscription
    subscription.status = 'active'
    subscription.starts_on, subscription.expires_on = start, end
    subscription.requires_activation = True
    subscription.key_enabled = True
    subscription.activated_at = timezone.now()
    subscription.save(update_fields=['status', 'starts_on', 'expires_on', 'requires_activation', 'key_enabled', 'activated_at'])
    OfflineLicense.objects.update_or_create(workspace=workspace, defaults={'signed_key': value.strip(), 'last_seen_date': today})
    AuditEvent.objects.create(workspace=workspace, actor=workspace.owner, action='subscription.offline_activated', details={'expires_on': str(end)})
    login(request, workspace.owner, backend='django.contrib.auth.backends.ModelBackend')
    return subscription
