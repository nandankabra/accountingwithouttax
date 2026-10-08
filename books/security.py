import hashlib
import logging
import re
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone


def bucket_key(scope,identity):
    return hashlib.sha256(f'{scope}:{identity}'.encode()).hexdigest()


@transaction.atomic
def consume_limit(scope,identity,limit,seconds=900):
    """A shared PostgreSQL counter, safe across workers and concurrent requests."""
    from .models import AuthThrottle
    key=bucket_key(scope,identity)
    now=timezone.now()
    AuthThrottle.objects.get_or_create(key=key,defaults={'window_start':now})
    bucket=AuthThrottle.objects.select_for_update().get(key=key)
    if now-bucket.window_start>=timedelta(seconds=seconds):
        bucket.window_start=now
        bucket.attempts=0
    if bucket.attempts>=limit:
        return False
    bucket.attempts+=1
    bucket.save(update_fields=['attempts','window_start'])
    return True


def login_allowed(request,email):
    return consume_limit('login-ip',request.META.get('REMOTE_ADDR',''),settings.LOGIN_IP_LIMIT) and consume_limit('login-account',email,10)


def clear_login_limit(email):
    from .models import AuthThrottle
    AuthThrottle.objects.filter(pk=bucket_key('login-account',email)).delete()


class RedactResetTokens(logging.Filter):
    def filter(self,record):
        record.msg=re.sub(r'/password-reset/confirm/[^/\s]+/[^/\s]+/', '/password-reset/confirm/[redacted]/', record.getMessage())
        record.args=()
        return True
