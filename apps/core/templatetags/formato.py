"""Filtros de plantilla para formato monetario y de estado."""
from decimal import Decimal

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name="mxn")
def mxn(valor) -> str:
    """Formatea un importe como pesos mexicanos: $1,234.56"""
    if valor in (None, ""):
        valor = Decimal("0")
    try:
        valor = Decimal(str(valor))
    except Exception:  # noqa: BLE001
        return str(valor)
    return f"${valor:,.2f}"


@register.filter(name="mxn_corto")
def mxn_corto(valor) -> str:
    """Formato compacto para tarjetas del dashboard: $1.2M, $15.3k"""
    try:
        valor = Decimal(str(valor or 0))
    except Exception:  # noqa: BLE001
        return str(valor)
    signo = "-" if valor < 0 else ""
    valor = abs(valor)
    if valor >= 1_000_000:
        return f"{signo}${valor / 1_000_000:.1f}M"
    if valor >= 10_000:
        return f"{signo}${valor / 1000:.1f}k"
    return f"{signo}${valor:,.2f}"


@register.filter(name="badge")
def badge(estado, mapa_css: str = "") -> str:
    """Devuelve la clase CSS del badge de un estado."""
    clases = {
        "borrador": "secondary",
        "pendiente": "warning",
        "pendiente_aprobacion": "warning",
        "aprobado": "info",
        "desembolsado": "primary",
        "activo": "success",
        "en_mora": "danger",
        "liquidado": "dark",
        "cancelado": "secondary",
        "reestructurado": "info",
        "parcial": "warning",
        "pagada": "success",
        "vencida": "danger",
        "confirmado": "success",
        "reversado": "secondary",
        "anulado": "secondary",
        "inactivo": "secondary",
        "restringido": "danger",
    }
    return mark_safe(clases.get(str(estado), "secondary"))  # noqa: S308


@register.filter(name="porcentaje")
def porcentaje(valor) -> str:
    try:
        return f"{Decimal(str(valor or 0)):.1f}%"
    except Exception:  # noqa: BLE001
        return "0.0%"


@register.filter(name="get_item")
def get_item(diccionario, clave):
    if hasattr(diccionario, "get"):
        return diccionario.get(clave)
    return None
