"""Clasificacion de cartera y calculo de mora.

Definiciones (ver docs/reglas_financieras.md):

* Dias de atraso de una CUOTA: dias naturales entre su vencimiento y hoy,
  si aun tiene saldo.
* Dias de atraso del CREDITO: los dias de su cuota vencida mas antigua.
* Saldo vencido: suma de los saldos de las cuotas ya vencidas.
* Saldo total pendiente: todo lo que falta por pagar del contrato,
  vencido o no.

El sistema NO agrega cargos moratorios automaticos: solo los calcula si
el negocio tiene una politica configurada y activada.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Min, Q, Sum

from apps.core.dinero import CERO, a_decimal, q
from apps.core.fechas import hoy_local
from apps.creditos.models import Credito, Cuota, EstadoCuota

SALDO_CUOTA = ExpressionWrapper(
    F("importe_programado") - F("importe_pagado"),
    output_field=DecimalField(max_digits=12, decimal_places=2),
)


def cuotas_de(creditos_qs):
    return Cuota.objects.filter(credito__in=creditos_qs)


def saldo_vencido_queryset(creditos_qs, hoy: dt.date | None = None) -> Decimal:
    """Suma de los saldos de cuotas vencidas de un conjunto de creditos."""
    hoy = hoy or hoy_local()
    total = (
        cuotas_de(creditos_qs)
        .filter(fecha_vencimiento__lt=hoy)
        .exclude(estado=EstadoCuota.PAGADA)
        .aggregate(total=Sum(SALDO_CUOTA))["total"]
    )
    return q(total or CERO)


def cuotas_que_vencen(creditos_qs, fecha: dt.date | None = None):
    fecha = fecha or hoy_local()
    return (
        cuotas_de(creditos_qs)
        .filter(fecha_vencimiento=fecha)
        .exclude(estado=EstadoCuota.PAGADA)
        .select_related("credito", "credito__cliente", "credito__cobrador")
        .order_by("credito__cliente__apellido_paterno")
    )


def cuotas_proximas(creditos_qs, dias: int = 7, desde: dt.date | None = None):
    desde = desde or hoy_local()
    hasta = desde + dt.timedelta(days=dias)
    return (
        cuotas_de(creditos_qs)
        .filter(fecha_vencimiento__gt=desde, fecha_vencimiento__lte=hasta)
        .exclude(estado=EstadoCuota.PAGADA)
        .select_related("credito", "credito__cliente", "credito__cobrador")
        .order_by("fecha_vencimiento")
    )


def cuotas_vencidas(creditos_qs, hoy: dt.date | None = None, dias_minimos: int = 0):
    hoy = hoy or hoy_local()
    limite = hoy - dt.timedelta(days=dias_minimos)
    return (
        cuotas_de(creditos_qs)
        .filter(fecha_vencimiento__lt=limite)
        .exclude(estado=EstadoCuota.PAGADA)
        .select_related("credito", "credito__cliente", "credito__cobrador")
        .order_by("fecha_vencimiento")
    )


def creditos_en_mora(creditos_qs, hoy: dt.date | None = None, dias_gracia: int = 0):
    hoy = hoy or hoy_local()
    limite = hoy - dt.timedelta(days=dias_gracia)
    return creditos_qs.filter(
        Q(cuotas__fecha_vencimiento__lt=limite) & ~Q(cuotas__estado=EstadoCuota.PAGADA)
    ).distinct()


def resumen_mora_por_credito(creditos_qs, hoy: dt.date | None = None) -> list[dict]:
    """Una fila por credito con cuotas vencidas: atraso, saldo vencido y total."""
    hoy = hoy or hoy_local()
    filas = (
        cuotas_de(creditos_qs)
        .filter(fecha_vencimiento__lt=hoy)
        .exclude(estado=EstadoCuota.PAGADA)
        .values("credito_id")
        .annotate(
            cuotas_vencidas=Count("id"),
            saldo_vencido=Sum(SALDO_CUOTA),
            vencimiento_mas_antiguo=Min("fecha_vencimiento"),
        )
    )
    indice = {fila["credito_id"]: fila for fila in filas}
    creditos = (
        creditos_qs.filter(pk__in=indice.keys())
        .select_related("cliente", "cobrador", "negocio")
    )
    resultado = []
    for credito in creditos:
        fila = indice[credito.pk]
        resultado.append({
            "credito": credito,
            "cliente": credito.cliente,
            "cuotas_vencidas": fila["cuotas_vencidas"],
            "saldo_vencido": q(fila["saldo_vencido"] or CERO),
            "saldo_total": q(credito.saldo_pendiente),
            "dias_atraso": (hoy - fila["vencimiento_mas_antiguo"]).days,
            "ultima_gestion": credito.gestiones.order_by("-fecha").first(),
        })
    resultado.sort(key=lambda fila: fila["dias_atraso"], reverse=True)
    return resultado



def calcular_cargo_moratorio(credito: Credito, hoy: dt.date | None = None) -> Decimal:
    """Cargo moratorio SOLO si el negocio lo tiene configurado y activado.

    No se guarda ni se cobra automaticamente: es un calculo informativo
    que requiere una politica documentada y una decision del negocio.
    """
    negocio = credito.negocio
    if not negocio.aplica_mora or a_decimal(negocio.tasa_mora) <= CERO:
        return CERO
    hoy = hoy or hoy_local()
    limite = hoy - dt.timedelta(days=negocio.dias_gracia)
    total = CERO
    for cuota in credito.cuotas.filter(fecha_vencimiento__lt=limite).exclude(
        estado=EstadoCuota.PAGADA
    ):
        dias = (limite - cuota.fecha_vencimiento).days
        total += a_decimal(cuota.saldo) * a_decimal(negocio.tasa_mora) * dias
    return q(total)


def clasificacion_cartera(creditos_qs, hoy: dt.date | None = None) -> dict:
    """Conteos y saldos por categoria de cartera."""
    from apps.creditos.models import EstadoCredito

    hoy = hoy or hoy_local()
    vigentes = creditos_qs.vigentes()
    return {
        "vencen_hoy": cuotas_que_vencen(vigentes, hoy).count(),
        "proximas": cuotas_proximas(vigentes, 7, hoy).count(),
        "vencidas": cuotas_vencidas(vigentes, hoy).count(),
        "creditos_en_mora": vigentes.filter(estado=EstadoCredito.EN_MORA).count(),
        "creditos_activos": vigentes.count(),
        "creditos_liquidados": creditos_qs.liquidados().count(),
        "saldo_vencido": saldo_vencido_queryset(vigentes, hoy),
        "saldo_total": q(
            vigentes.aggregate(t=Sum("saldo_pendiente"))["t"] or CERO),
        "clientes_multiples_creditos": (
            vigentes.values("cliente_id")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
            .count()
        ),
        "parcialmente_pagados": vigentes.filter(
            Q(capital_pagado__gt=0) | Q(interes_pagado__gt=0)
        ).count(),
    }
