from urllib.parse import urlsplit
from django.conf import settings
from django.core.checks import Error,register,Tags


@register(Tags.security,deploy=True)
def production_account_config(app_configs,**kwargs):
    errors=[]
    if not settings.DEBUG:
        site=urlsplit(settings.APP_PUBLIC_URL)
        if site.scheme!='https' or not site.netloc or site.username or site.password:
            errors.append(Error('Set APP_PUBLIC_URL to the canonical HTTPS application origin.',id='books.E001'))
        if not settings.EMAIL_HOST or settings.EMAIL_BACKEND!='django.core.mail.backends.smtp.EmailBackend':
            errors.append(Error('Configure an SMTP email service for production password recovery.',id='books.E002'))
        if settings.DEFAULT_FROM_EMAIL.endswith('example.test>'):
            errors.append(Error('Configure a verified DEFAULT_FROM_EMAIL sender for password recovery.',id='books.E003'))
    return errors
