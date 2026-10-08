from django import forms
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render,redirect
from .models import Workspace,AuditEvent
from .subscriptions import access


class CompanyForm(forms.ModelForm):
    version=forms.IntegerField(widget=forms.HiddenInput)
    class Meta:
        model=Workspace
        fields=['name','mobile','email','address','city','postcode']
        widgets={'address':forms.Textarea(attrs={'rows':3})}
        labels={'name':'Company name','mobile':'Mobile number','email':'Company email','postcode':'Postal code'}
    def clean_name(self):
        name=self.cleaned_data['name'].strip()
        if not name:raise forms.ValidationError('Enter a company name.')
        return name
    def clean_mobile(self):
        value=self.cleaned_data['mobile'].strip()
        if value and (not all(c.isdigit() or c in '+ -()' for c in value) or not 7<=sum(c.isdigit() for c in value)<=15):raise forms.ValidationError('Enter a valid mobile number, with country code if needed.')
        return value


@login_required
def company(request):
    if request.user.is_superuser:return redirect('/admin/')
    workspace=request.user.workspace
    form=CompanyForm(request.POST or None,instance=workspace,initial={'version':workspace.profile_version})
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            locked=Workspace.objects.select_for_update().get(pk=workspace.pk)
            if form.cleaned_data['version']!=locked.profile_version:
                form.add_error(None,'Company details changed on another device. Reload and review before saving.')
            else:
                before={field:getattr(locked,field) for field in form._meta.fields}
                for field in form._meta.fields:setattr(locked,field,form.cleaned_data[field])
                locked.profile_version+=1
                locked.save(update_fields=[*form._meta.fields,'profile_version'])
                AuditEvent.objects.create(workspace=locked,actor=request.user,action='company.updated',details={'before':before,'after':{field:getattr(locked,field) for field in form._meta.fields},'version':locked.profile_version})
                return redirect('/company/?saved=1')
    return render(request,'books/company.html',{'form':form,'workspace':workspace,'subscription':access(workspace)})
