import json
import logging
import time
import uuid
from django.http import JsonResponse

logger = logging.getLogger('simplebooks')


class RequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.reference_id = uuid.uuid4().hex[:12]
        start = time.monotonic()
        response = self.get_response(request)
        response['X-Request-ID'] = request.reference_id
        response['X-Frame-Options'] = 'DENY'
        response['Referrer-Policy'] = 'same-origin'
        response['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.user.is_authenticated or request.path.startswith('/api/'):
            response['Cache-Control'] = 'no-store'
        if request.path.startswith('/api/'):
            logger.info(json.dumps({'request_id': request.reference_id, 'method': request.method, 'status': response.status_code, 'duration_ms': round((time.monotonic()-start)*1000)}))
        return response

    def process_exception(self, request, exception):
        if request.path.startswith('/api/'):
            # Do not log payloads, passwords, or exception strings containing SQL values.
            logger.error(json.dumps({'request_id': request.reference_id, 'error_type': type(exception).__name__}))
            return JsonResponse({'error': 'The request could not be completed. Your records were not partially posted.', 'reference_id': request.reference_id}, status=500)
