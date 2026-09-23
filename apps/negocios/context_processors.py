from apps.usuarios import permisos


def negocios_disponibles(request):
    """Expone en todas las plantillas los negocios autorizados y los permisos.

    ``permisos_usuario`` es un diccionario {accion: bool} para que las
    plantillas puedan ocultar opciones del menu. Ocultar NO sustituye la
    validacion en el servidor: cada vista vuelve a verificar el permiso.
    """
    usuario = getattr(request, "user", None)
    if not usuario or not usuario.is_authenticated:
        return {}
    return {
        "negocios_usuario": permisos.negocios_permitidos(usuario).activos(),
        "permisos_usuario": {
            accion: permisos.puede(usuario, accion) for accion in permisos.MATRIZ
        },
    }
