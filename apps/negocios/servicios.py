"""Indicadores agregados por negocio.

Centraliza las consultas de cartera para que el dashboard del negocio,
el dashboard general y los reportes usen exactamente las mismas
definiciones (ver docs/reglas_financieras.md).
"""
from decimal import Decimal

from django.db.models import Count, Q, Sum

from apps.core.dinero import CERO, q


def resumen_negocio(negocio, desde=None, hasta=None) -> dict:
    """Indicadores principales de un negocio.

    * capital_colocado: suma del capital de creditos desembolsados.
    * interes_contractual: interes pactado de esos creditos.
    * total_recaudado: pagos confirmados (no incluye pagos reversados).
    * saldo_pendiente: lo que falta por cobrar de creditos vigentes.
    * saldo_vencido: parte del saldo pendiente cuya fecha ya vencio.
    """
    from apps.creditos.models import ESTADOS_VIGENTES, Credito, EstadoCredito
    from apps.pagos.models import EstadoPago, Pago

    creditos = Credito.objects.filter(negocio=negocio).desembolsados()
    if desde:
        creditos = creditos.filter(fecha_desembolso__gte=desde)
    if hasta:
        creditos = creditos.filter(fecha_desembolso__lte=hasta)

    agregados = creditos.aggregate(
        capital=Sum("capital"),
        interes=Sum("interes_total"),
        total=Sum("total_a_pagar"),
        saldo=Sum("saldo_pendiente"),
        activos=Count("id", filter=Q(estado__in=ESTADOS_VIGENTES)),
        liquidados=Count("id", filter=Q(estado=EstadoCredito.LIQUIDADO)),
        en_mora=Count("id", filter=Q(estado=EstadoCredito.EN_MORA)),
    )

    pagos = Pago.objects.filter(negocio=negocio, estado=EstadoPago.CONFIRMADO)
    if desde:
        pagos = pagos.filter(fecha__date__gte=desde)
    if hasta:
        pagos = pagos.filter(fecha__date__lte=hasta)
    recaudado = pagos.aggregate(total=Sum("importe"))["total"] or CERO

    capital = agregados["capital"] or CERO
    interes = agregados["interes"] or CERO
    total = agregados["total"] or CERO
    saldo = agregados["saldo"] or CERO

    from apps.cobranza.servicios import saldo_vencido_queryset

    vencido = saldo_vencido_queryset(creditos)

    return {
        "negocio": negocio,
        "capital_colocado": q(capital),
        "interes_contractual": q(interes),
        "total_contractual": q(total),
        "total_recaudado": q(recaudado),
        "saldo_pendiente": q(saldo),
        "saldo_vencido": q(vencido),
        "creditos_activos": agregados["activos"] or 0,
        "creditos_liquidados": agregados["liquidados"] or 0,
        "creditos_en_mora": agregados["en_mora"] or 0,
        "porcentaje_recuperacion": porcentaje(recaudado, total),
        "porcentaje_cartera_vencida": porcentaje(vencido, saldo),
    }


def porcentaje(parte, total) -> Decimal:
    parte = parte or CERO
    total = total or CERO
    if total <= CERO:
        return CERO
    return q(Decimal(parte) * 100 / Decimal(total))
