from urllib.parse import urlsplit
from django.conf import settings
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.views import PasswordChangeView, PasswordResetView, PasswordResetConfirmView
from django.db import transaction
from django.shortcuts import redirect, render
from .models import AuditEvent, Workspace
from .security import consume_limit,clear_login_limit


def security_event(user,action,authenticated=True):
    workspace=Workspace.objects.filter(owner=user).first()
    if workspace:
        AuditEvent.objects.create(workspace=workspace,actor=user if authenticated else None,action=action,details={'account':user.username})


class ChangePassword(PasswordChangeView):
    template_name='books/security.html'
    success_url='/security/?changed=1'
    extra_context={'heading':'Keep your account secure.','subtitle':'Change your password. Other devices will need to sign in again.','button':'Change password'}

    def form_valid(self,form):
        with transaction.atomic():
            response=super().form_valid(form)
            security_event(self.request.user,'auth.password_changed')
        return response


class WorkspaceResetForm(PasswordResetForm):
    def get_users(self,email):
        for user in super().get_users(email):
            if Workspace.objects.filter(owner=user).exists():
                yield user


class RequestPasswordReset(PasswordResetView):
    form_class=WorkspaceResetForm
    template_name='books/security.html'
    email_template_name='books/password_reset_email.txt'
    subject_template_name='books/password_reset_subject.txt'
    success_url='/password-reset/sent/'
    extra_context={'heading':'Find your way back in.','subtitle':'Enter your workspace email to request a password reset.','button':'Send reset instructions'}

    def form_valid(self,form):
        email=form.cleaned_data['email'].lower()
        allowed=consume_limit('reset-ip',self.request.META.get('REMOTE_ADDR',''),30,3600) and consume_limit('reset-account',email,3,3600)
        if allowed:
            site=urlsplit(settings.APP_PUBLIC_URL)
            form.save(use_https=site.scheme=='https',domain_override=site.netloc,from_email=settings.DEFAULT_FROM_EMAIL,email_template_name=self.email_template_name,subject_template_name=self.subject_template_name,request=self.request)
            for user in form.get_users(email):security_event(user,'auth.reset_requested',False)
        return redirect(self.success_url)


class ConfirmPasswordReset(PasswordResetConfirmView):
    template_name='books/security.html'
    success_url='/password-reset/complete/'
    extra_context={'heading':'Choose a new password.','subtitle':'This reset link can be used once and expires after 15 minutes.','button':'Save new password','is_reset_confirm':True}

    def form_valid(self,form):
        with transaction.atomic():
            response=super().form_valid(form)
            clear_login_limit(self.user.username)
            security_event(self.user,'auth.password_reset')
        return response


def reset_sent(request):
    return render(request,'books/security.html',{'heading':'Check your email.','subtitle':'If an active workspace matches that address, reset instructions have been sent.','notice':'The link expires in 15 minutes. Check your spam folder as well.'})


def reset_complete(request):
    return render(request,'books/security.html',{'heading':'Password updated.','subtitle':'Sign in with your new password. Previous sessions are no longer valid.'})
