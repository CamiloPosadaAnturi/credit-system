"""Guarda la peticion actual en un contexto local al hilo.

Permite que la capa de servicios registre quien ejecuta una operacion
financiera sin tener que recibir el ``request`` como parametro.
"""
import threading

_local = threading.local()


class AuditoriaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.request = request
        try:
            return self.get_response(request)
        finally:
            _local.request = None


def peticion_actual():
    return getattr(_local, "request", None)


def usuario_actual():
    peticion = peticion_actual()
    if peticion is None:
        return None
    usuario = getattr(peticion, "user", None)
    if usuario is not None and usuario.is_authenticated:
        return usuario
    return None


def ip_actual():
    peticion = peticion_actual()
    if peticion is None:
        return None
    adelante = peticion.META.get("HTTP_X_FORWARDED_FOR")
    if adelante:
        return adelante.split(",")[0].strip()
    return peticion.META.get("REMOTE_ADDR")
