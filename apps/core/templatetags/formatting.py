"""Template filters for money and status formatting."""
from decimal import Decimal

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name="mxn")
def mxn(value) -> str:
    """Format an amount as Mexican pesos: $1,234.56"""
    if value in (None, ""):
        value = Decimal("0")
    try:
        value = Decimal(str(value))
    except Exception:  # noqa: BLE001
        return str(value)
    return f"${value:,.2f}"


@register.filter(name="mxn_short")
def mxn_short(value) -> str:
    """Compact format for dashboard tiles: $1.2M, $15.3k"""
    try:
        value = Decimal(str(value or 0))
    except Exception:  # noqa: BLE001
        return str(value)
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1_000_000:
        return f"{sign}${value / 1_000_000:.1f}M"
    if value >= 10_000:
        return f"{sign}${value / 1000:.1f}k"
    return f"{sign}${value:,.2f}"


@register.filter(name="badge")
def badge(status) -> str:
    """Return the Bootstrap contextual class for a status value."""
    classes = {
        "draft": "secondary",
        "pending_approval": "warning",
        "approved": "info",
        "disbursed": "primary",
        "active": "success",
        "past_due": "danger",
        "settled": "dark",
        "cancelled": "secondary",
        "restructured": "info",
        "partial": "warning",
        "paid": "success",
        "overdue": "danger",
        "confirmed": "success",
        "reversed": "secondary",
        "inactive": "secondary",
        "restricted": "danger",
    }
    return mark_safe(classes.get(str(status), "secondary"))  # noqa: S308


@register.filter(name="percent")
def percent(value) -> str:
    try:
        return f"{Decimal(str(value or 0)):.1f}%"
    except Exception:  # noqa: BLE001
        return "0.0%"


@register.filter(name="get_item")
def get_item(mapping, key):
    if hasattr(mapping, "get"):
        return mapping.get(key)
    return None
