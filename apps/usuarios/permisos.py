"""Matriz de permisos y utilidades de aislamiento de datos por negocio.

Toda validacion de permisos se aplica en el servidor: en las vistas
(que accion se permite) y en el ORM (que filas se pueden ver). Ocultar
botones en el frontend NO es un control de seguridad.
"""
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet

from apps.usuarios.models import Rol

# --- Acciones del sistema -------------------------------------------------
VER_DASHBOARD = "ver_dashboard"
GESTIONAR_NEGOCIOS = "gestionar_negocios"
GESTIONAR_USUARIOS = "gestionar_usuarios"
VER_CLIENTES = "ver_clientes"
GESTIONAR_CLIENTES = "gestionar_clientes"
VER_DATOS_SENSIBLES = "ver_datos_sensibles"
VER_CREDITOS = "ver_creditos"
CREAR_CREDITO = "crear_credito"
APROBAR_CREDITO = "aprobar_credito"
DESEMBOLSAR_CREDITO = "desembolsar_credito"
CANCELAR_CREDITO = "cancelar_credito"
REESTRUCTURAR_CREDITO = "reestructurar_credito"
VER_PAGOS = "ver_pagos"
REGISTRAR_PAGO = "registrar_pago"
REVERSAR_PAGO = "reversar_pago"
VER_COBRANZA = "ver_cobranza"
REGISTRAR_GESTION = "registrar_gestion"
VER_REPORTES = "ver_reportes"
VER_AUDITORIA = "ver_auditoria"

TODOS = {Rol.SUPERADMIN, Rol.ADMIN, Rol.GERENTE, Rol.COBRADOR, Rol.CONSULTA}

MATRIZ: dict[str, set[str]] = {
    VER_DASHBOARD: TODOS,
    GESTIONAR_NEGOCIOS: {Rol.SUPERADMIN, Rol.ADMIN},
    GESTIONAR_USUARIOS: {Rol.SUPERADMIN, Rol.ADMIN},
    VER_CLIENTES: TODOS,
    GESTIONAR_CLIENTES: {Rol.SUPERADMIN, Rol.ADMIN, Rol.GERENTE},
    VER_DATOS_SENSIBLES: {Rol.SUPERADMIN, Rol.ADMIN},
    VER_CREDITOS: TODOS,
    CREAR_CREDITO: {Rol.SUPERADMIN, Rol.ADMIN, Rol.GERENTE},
    APROBAR_CREDITO: {Rol.SUPERADMIN, Rol.ADMIN},
    DESEMBOLSAR_CREDITO: {Rol.SUPERADMIN, Rol.ADMIN},
    CANCELAR_CREDITO: {Rol.SUPERADMIN, Rol.ADMIN},
    REESTRUCTURAR_CREDITO: {Rol.SUPERADMIN, Rol.ADMIN},
    VER_PAGOS: TODOS,
    REGISTRAR_PAGO: {Rol.SUPERADMIN, Rol.ADMIN, Rol.GERENTE, Rol.COBRADOR},
    REVERSAR_PAGO: {Rol.SUPERADMIN, Rol.ADMIN},
    VER_COBRANZA: {Rol.SUPERADMIN, Rol.ADMIN, Rol.GERENTE, Rol.COBRADOR},
    REGISTRAR_GESTION: {Rol.SUPERADMIN, Rol.ADMIN, Rol.GERENTE, Rol.COBRADOR},
    VER_REPORTES: {Rol.SUPERADMIN, Rol.ADMIN, Rol.GERENTE},
    VER_AUDITORIA: {Rol.SUPERADMIN, Rol.ADMIN},
}


def puede(usuario, accion: str) -> bool:
    if not usuario or not usuario.is_authenticated or not usuario.is_active:
        return False
    if getattr(usuario, "es_superadmin", False):
        return True
    roles = MATRIZ.get(accion)
    if roles is None:
        raise ValueError(f"Accion desconocida en la matriz de permisos: {accion}")
    return usuario.rol in roles


def exigir(usuario, accion: str) -> None:
    if not puede(usuario, accion):
        raise PermissionDenied(f"No tienes autorizacion para: {accion}")


def negocios_permitidos(usuario) -> QuerySet:
    """Negocios sobre los que el usuario puede operar."""
    from apps.negocios.models import Negocio

    if not usuario or not usuario.is_authenticated:
        return Negocio.objects.none()
    if usuario.es_superadmin:
        return Negocio.objects.all()
    return Negocio.objects.filter(usuarios=usuario).distinct()


def ids_negocios_permitidos(usuario) -> list[int]:
    return list(negocios_permitidos(usuario).values_list("id", flat=True))


def filtrar_por_negocio(queryset: QuerySet, usuario, campo: str = "negocio") -> QuerySet:
    """Restringe un queryset a los negocios autorizados del usuario."""
    if usuario and getattr(usuario, "es_superadmin", False):
        return queryset
    return queryset.filter(**{f"{campo}__in": negocios_permitidos(usuario)})


def filtrar_cartera_cobrador(queryset: QuerySet, usuario, campo: str = "cobrador") -> QuerySet:
    """Un cobrador solo ve la cartera que tiene asignada."""
    if usuario and getattr(usuario, "es_cobrador", False):
        return queryset.filter(**{campo: usuario})
    return queryset


def usuario_tiene_negocio(usuario, negocio) -> bool:
    if usuario.es_superadmin:
        return True
    return negocios_permitidos(usuario).filter(pk=negocio.pk).exists()


def exigir_negocio(usuario, negocio) -> None:
    if not usuario_tiene_negocio(usuario, negocio):
        raise PermissionDenied("No tienes acceso a este negocio.")
