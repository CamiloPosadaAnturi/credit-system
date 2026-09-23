from apps.notificaciones.servicios import notificaciones_de


def notificaciones_pendientes(request):
    usuario = getattr(request, "user", None)
    if not usuario or not usuario.is_authenticated:
        return {}
    pendientes = notificaciones_de(usuario)[:10]
    return {
        "notificaciones_pendientes": pendientes,
        "notificaciones_pendientes_total": notificaciones_de(usuario).count(),
    }
