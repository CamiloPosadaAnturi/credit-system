from apps.notificaciones.models import Notificacion, TipoNotificacion


def crear_notificacion(*, negocio, titulo: str, mensaje: str = "", url: str = "",
                       usuario=None, tipo: str = TipoNotificacion.INFORMATIVA):
    return Notificacion.objects.create(
        negocio=negocio, usuario=usuario, titulo=titulo[:150],
        mensaje=mensaje, url=url, tipo=tipo,
    )


def notificaciones_de(usuario, solo_no_leidas: bool = True):
    from apps.usuarios import permisos

    qs = Notificacion.objects.filter(negocio__in=permisos.negocios_permitidos(usuario))
    qs = qs.filter(usuario__in=[usuario, None])
    if solo_no_leidas:
        qs = qs.filter(leida=False)
    return qs
