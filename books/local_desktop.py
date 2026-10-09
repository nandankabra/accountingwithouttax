import hmac
from django.conf import settings
from django.contrib.auth import login
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST


class LocalOnlyMiddleware:
    """Keep unrelated local programs/browser tabs out of the private service."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = request.headers.get('X-SimpleBooks-Local', '')
        if request.META.get('REMOTE_ADDR') != '127.0.0.1' or not hmac.compare_digest(token, settings.LOCAL_SERVICE_TOKEN):
            return HttpResponse('This service is available only inside the installed app.', status=403)
        if request.path.startswith(('/admin/', '/signup/', '/password-reset/', '/security/')):
            return HttpResponse('This feature is managed by your provider.', status=404)
        return self.get_response(request)


class LocalSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            from .models import OfflineLicense
            from .offline_licensing import licence_access
            state = OfflineLicense.objects.select_related('workspace__owner').first()
            if state and state.workspace.owner.is_active and not state.workspace.owner.is_superuser and licence_access(state.workspace)[0]:
                login(request, state.workspace.owner, backend='django.contrib.auth.backends.ModelBackend')
        return self.get_response(request)


@require_POST
def resume(request):
    if not getattr(settings, 'LOCAL_DESKTOP', False):
        return JsonResponse({'error': 'Unavailable'}, status=404)
    from .models import OfflineLicense
    from .offline_licensing import licence_access
    state = OfflineLicense.objects.select_related('workspace__owner').first()
    if not state or not licence_access(state.workspace)[0]:
        return JsonResponse({'activated': False})
    login(request, state.workspace.owner, backend='django.contrib.auth.backends.ModelBackend')
    return JsonResponse({'activated': True})
