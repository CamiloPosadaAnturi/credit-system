"""Keep the current request in a thread-local context.

This lets the service layer record who runs a financial operation without
having to pass the ``request`` around as a parameter.
"""
import threading

_local = threading.local()


class AuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.request = request
        try:
            return self.get_response(request)
        finally:
            _local.request = None


def current_request():
    return getattr(_local, "request", None)


def current_user():
    request = current_request()
    if request is None:
        return None
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return user
    return None


def current_ip():
    request = current_request()
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
