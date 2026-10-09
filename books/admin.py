from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect
from django.shortcuts import render,get_object_or_404
from django.urls import path,reverse
from django.utils.html import format_html
from .company import CompanyForm
from .models import Workspace,SubscriptionPlan,Subscription,AuditEvent
from .services import create_workspace


class ProviderSite(admin.AdminSite):
    site_header='Simple Books · Product administration'
    site_title='Simple Books administration'
    index_title='Customers and subscriptions'
    def has_permission(self,request):return request.user.is_active and request.user.is_superuser
    def login(self,request,extra_context=None):
        if self.has_permission(request):return redirect('/admin/')
        if request.user.is_authenticated:return HttpResponse('Product administration is available to the service provider only.',status=403)
        # Reuse the shared, rate-limited login instead of an unthrottled admin login.
        return redirect('/login/')


provider_site=ProviderSite(name='provider')


class CustomerForm(forms.ModelForm):
    customer_email=forms.EmailField(max_length=150,label='Customer login email',required=False)
    password1=forms.CharField(widget=forms.PasswordInput,required=False,label='Initial password')
    password2=forms.CharField(widget=forms.PasswordInput,required=False,label='Confirm initial password')
    class Meta:
        model=Workspace
        fields=['name','mobile','address','email','city','postcode']
    clean_name=CompanyForm.clean_name
    clean_mobile=CompanyForm.clean_mobile
    def clean(self):
        data=super().clean()
        if self.instance._state.adding:
            email=data.get('customer_email','').lower()
            if not email:self.add_error('customer_email','Enter the customer login email.')
            elif User.objects.filter(username__iexact=email).exists():self.add_error('customer_email','This login already exists.')
            password=data.get('password1','')
            if password!=data.get('password2'):self.add_error('password2','Passwords must match.')
            try:validate_password(password,User(username=email,email=email))
            except forms.ValidationError as error:self.add_error('password1',error)
            data['customer_email']=email
        return data


@admin.register(Workspace,site=provider_site)
class CustomerAdmin(admin.ModelAdmin):
    form=CustomerForm
    list_display=['name','login_email','mobile','subscription_status','expiry']
    search_fields=['name','owner__username','mobile']
    list_per_page=25
    def get_queryset(self,request):return super().get_queryset(request).select_related('owner','subscription')
    def login_email(self,obj):return obj.owner.username
    def subscription_status(self,obj):return obj.subscription.status
    def expiry(self,obj):return obj.subscription.expires_on
    def get_fields(self,request,obj=None):
        fields=['name','mobile','address','email','city','postcode']
        return fields if obj else fields+['customer_email','password1','password2']
    def has_delete_permission(self,request,obj=None):return False
    @transaction.atomic
    def save_model(self,request,obj,form,change):
        if not change:
            user=User.objects.create_user(form.cleaned_data['customer_email'],email=form.cleaned_data['customer_email'],password=form.cleaned_data['password1'])
            workspace=create_workspace(user,obj.name)
            for field in ['mobile','address','email','city','postcode']:setattr(workspace,field,getattr(obj,field))
            workspace.save()
            subscription=workspace.subscription
            subscription.requires_activation=True;subscription.status='suspended';subscription.expires_on=subscription.starts_on
            subscription.save(update_fields=['requires_activation','status','expires_on'])
            obj.__dict__.update(workspace.__dict__)
        else:
            locked=Workspace.objects.select_for_update().get(pk=obj.pk)
            fields=['name','mobile','address','email','city','postcode']
            for field in fields:setattr(locked,field,getattr(obj,field))
            locked.profile_version+=1
            locked.save(update_fields=[*fields,'profile_version'])
            obj.__dict__.update(locked.__dict__)
        AuditEvent.objects.create(workspace=obj,actor=request.user,action='provider.company_saved',details={'name':obj.name,'created':not change})


@admin.register(SubscriptionPlan,site=provider_site)
class PlanAdmin(admin.ModelAdmin):
    list_display=['name','price','duration_days','active']
    def formfield_for_dbfield(self,db_field,request,**kwargs):
        field=super().formfield_for_dbfield(db_field,request,**kwargs)
        if db_field.name=='price':
            field.label='Price · INR'
            field.help_text='Plan price for your records. Collect payments separately.'
        if db_field.name=='duration_days':field.help_text='Use this duration when setting the customer subscription expiry.'
        return field
    def has_delete_permission(self,request,obj=None):return False


@admin.register(Subscription,site=provider_site)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display=['workspace','plan','status','starts_on','expires_on']
    list_filter=['status','plan']
    search_fields=['workspace__name','workspace__owner__username']
    autocomplete_fields=['workspace']
    list_per_page=25
    list_select_related=['workspace','plan']
    fields=['workspace','plan','status','starts_on','expires_on','notes','requires_activation','key_enabled','key_version','activated_at','activation_key_controls']
    def get_urls(self):
        return [path('<int:object_id>/issue-key/',self.admin_site.admin_view(self.issue_key_view),name='books_subscription_issue_key')]+super().get_urls()
    @admin.display(description='Subscription key')
    def activation_key_controls(self,obj):
        return format_html('<a class="button" href="{}">Generate / replace subscription key</a>',reverse('provider:books_subscription_issue_key',args=[obj.pk]))
    def issue_key_view(self,request,object_id):
        from .licensing import issue_key
        obj=get_object_or_404(Subscription.objects.select_related('workspace'),pk=object_id)
        key=None;error=None
        if request.method=='POST':
            try:key=issue_key(obj,request.user)
            except ValueError as exc:error=str(exc)
            obj.refresh_from_db()
        return render(request,'admin/books/issue_key.html',{**self.admin_site.each_context(request),'opts':self.model._meta,'title':'Subscription key','subscription':obj,'key':key,'error':error,'back_url':reverse('provider:books_subscription_change',args=[obj.pk])})
    def formfield_for_dbfield(self,db_field,request,**kwargs):
        field=super().formfield_for_dbfield(db_field,request,**kwargs)
        if db_field.name=='plan':
            field.widget.can_add_related=False
            field.widget.can_change_related=False
            field.widget.can_delete_related=False
            field.widget.can_view_related=False
        return field
    def has_add_permission(self,request):return False
    def has_delete_permission(self,request,obj=None):return False
    def get_readonly_fields(self,request,obj=None):return ['workspace','requires_activation','key_version','activated_at','activation_key_controls']
    @transaction.atomic
    def save_model(self,request,obj,form,change):
        # Match the posting lock so suspension and new postings have a clear order.
        Workspace.objects.select_for_update().get(pk=obj.workspace_id)
        obj.save(update_fields=['plan','status','starts_on','expires_on','notes','key_enabled'])
        AuditEvent.objects.create(workspace=obj.workspace,actor=request.user,action='provider.subscription_updated',details={'status':obj.status,'plan':obj.plan_id,'starts_on':str(obj.starts_on),'expires_on':str(obj.expires_on),'key_enabled':obj.key_enabled,'notes':obj.notes})


class ProviderUserAdmin(UserAdmin):
    def has_delete_permission(self,request,obj=None):return False
    def has_add_permission(self,request):return False

provider_site.register(User,ProviderUserAdmin)
