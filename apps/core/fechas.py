"""Utilidades de fechas para los calendarios de pago.

Se implementa ``sumar_meses`` sin dependencias externas para evitar
comportamientos inesperados con dias 29, 30 y 31.
"""
import calendar
import datetime as dt


def sumar_meses(fecha: dt.date, meses: int) -> dt.date:
    """Suma meses conservando el dia; si el mes destino es mas corto, usa su ultimo dia.

    Ejemplo: 31/01 + 1 mes -> 28/02 (o 29/02 en anio bisiesto).
    """
    total = fecha.month - 1 + meses
    anio = fecha.year + total // 12
    mes = total % 12 + 1
    dia = min(fecha.day, calendar.monthrange(anio, mes)[1])
    return dt.date(anio, mes, dia)


def sumar_dias(fecha: dt.date, dias: int) -> dt.date:
    return fecha + dt.timedelta(days=dias)


def hoy_local() -> dt.date:
    """Fecha de hoy en la zona horaria configurada (America/Mexico_City)."""
    from django.utils import timezone

    return timezone.localdate()


def ahora_local():
    from django.utils import timezone

    return timezone.localtime()
