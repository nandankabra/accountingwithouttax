import json
import logging
import time
import uuid
from datetime import datetime, timezone
from django.http import JsonResponse

logger = logging.getLogger('simplebooks')


class RequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.reference_id = uuid.uuid4().hex[:12]
        start = time.monotonic()
        version=request.session.get('subscription_key_version')
        if request.user.is_authenticated and version is not None:
            from django.contrib.auth import logout
            from .models import Subscription
            subscription=Subscription.objects.filter(workspace__owner=request.user).first()
            if request.user.is_superuser or not subscription or not subscription.key_enabled or subscription.key_version!=version:logout(request)
        response = self.get_response(request)
        response['X-Request-ID'] = request.reference_id
        response['X-Frame-Options'] = 'DENY'
        response['Referrer-Policy'] = 'same-origin'
        response['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.user.is_authenticated or request.path.startswith('/api/'):
            response['Cache-Control'] = 'no-store'
        if request.path.startswith('/api/'):
            duration = round((time.monotonic()-start)*1000,2)
            response['Server-Timing'] = f'app;dur={duration}'
            route = request.resolver_match.route if request.resolver_match else 'unresolved'
            logger.info(json.dumps({'timestamp':datetime.now(timezone.utc).isoformat(),'request_id': request.reference_id, 'route':route,'method': request.method, 'status': response.status_code, 'duration_ms': duration}))
        return response

    def process_exception(self, request, exception):
        if request.path.startswith('/api/'):
            # Do not log payloads, passwords, or exception strings containing SQL values.
            logger.error(json.dumps({'timestamp':datetime.now(timezone.utc).isoformat(),'request_id': request.reference_id, 'error_type': type(exception).__name__}))
            return JsonResponse({'error': 'The request could not be completed. Your records were not partially posted.', 'reference_id': request.reference_id}, status=500)
