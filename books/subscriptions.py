from django.utils import timezone
from django.conf import settings
from .engine import PostingError


def access(workspace):
    subscription=workspace.subscription
    today=timezone.localdate()
    activated=not subscription.requires_activation or (subscription.key_enabled and subscription.activated_at is not None)
    allowed=activated and subscription.status in ('active','trial') and subscription.starts_on<=today<=subscription.expires_on
    if getattr(settings, 'LOCAL_DESKTOP', False):
        from .offline_licensing import licence_access
        activated, signed_allowed = licence_access(workspace)
        allowed = allowed and signed_allowed
    return {'status':subscription.status,'plan':subscription.plan.name if subscription.plan_id else 'Trial' if subscription.status=='trial' else 'Custom plan','starts_on':subscription.starts_on,'expires_on':subscription.expires_on,'can_write':allowed,'requires_activation':subscription.requires_activation,'activated':activated}


def ensure_can_write(workspace):
    if not access(workspace)['can_write']:
        raise PostingError('Activate your subscription key or contact your provider to renew an inactive subscription. You can still view and export your books.',status=403)
