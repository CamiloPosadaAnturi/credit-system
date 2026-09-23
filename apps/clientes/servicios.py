"""Historial e indicadores de comportamiento de pago de un cliente."""
from decimal import Decimal

from django.db.models import Count, F, Q, Sum

from apps.core.dinero import CERO, q
from apps.core.fechas import hoy_local


def resumen_cliente(cliente) -> dict:
    """Historial crediticio interno del cliente.

    Es informacion para que una persona decida: el sistema no aprueba ni
    rechaza automaticamente con base en un puntaje.
    """
    from apps.creditos.models import ESTADOS_DESEMBOLSADOS, EstadoCredito, EstadoCuota
    from apps.pagos.models import EstadoPago, Pago

    creditos = cliente.creditos.all()
    agregados = creditos.aggregate(
        total=Count("id"),
        vigentes=Count("id", filter=Q(estado__in=[EstadoCredito.DESEMBOLSADO,
                                                  EstadoCredito.ACTIVO,
                                                  EstadoCredito.EN_MORA])),
        liquidados=Count("id", filter=Q(estado=EstadoCredito.LIQUIDADO)),
        reestructurados=Count("id", filter=Q(estado=EstadoCredito.REESTRUCTURADO)),
        capital_historico=Sum("capital", filter=Q(estado__in=ESTADOS_DESEMBOLSADOS)),
        saldo=Sum("saldo_pendiente"),
    )

    pagado = Pago.objects.filter(
        cliente=cliente, estado=EstadoPago.CONFIRMADO
    ).aggregate(total=Sum("importe"))["total"] or CERO

    cuotas = _cuotas_del_cliente(cliente)
    hoy = hoy_local()
    vencidas = cuotas.filter(fecha_vencimiento__lt=hoy).exclude(estado=EstadoCuota.PAGADA)
    pagadas = cuotas.filter(estado=EstadoCuota.PAGADA)
    pagadas_a_tiempo = pagadas.filter(
        fecha_liquidacion__lte=F("fecha_vencimiento")
    ).count()
    total_pagadas = pagadas.count()

    saldo_vencido = CERO
    dias_atraso_max = 0
    for cuota in vencidas.select_related("credito"):
        saldo_vencido += cuota.saldo
        dias_atraso_max = max(dias_atraso_max, cuota.dias_atraso)

    puntualidad = (
        Decimal(pagadas_a_tiempo * 100) / Decimal(total_pagadas)
        if total_pagadas
        else CERO
    )

    return {
        "cliente": cliente,
        "creditos_total": agregados["total"] or 0,
        "creditos_vigentes_num": agregados["vigentes"] or 0,
        "creditos_liquidados": agregados["liquidados"] or 0,
        "creditos_reestructurados": agregados["reestructurados"] or 0,
        "total_solicitado": q(agregados["capital_historico"] or CERO),
        "total_pagado": q(pagado),
        "saldo_pendiente": q(agregados["saldo"] or CERO),
        "saldo_vencido": q(saldo_vencido),
        "cuotas_vencidas": vencidas.count(),
        "cuotas_pagadas": total_pagadas,
        "cuotas_pagadas_a_tiempo": pagadas_a_tiempo,
        "dias_atraso_maximo": dias_atraso_max,
        "puntualidad": q(puntualidad),
    }



def _cuotas_del_cliente(cliente):
    from apps.creditos.models import Cuota

    return Cuota.objects.filter(credito__cliente=cliente)


def historial_pagos(cliente, limite: int | None = None):
    from apps.pagos.models import Pago

    qs = (
        Pago.objects.filter(cliente=cliente)
        .select_related("credito")
        .order_by("-fecha")
    )
    return qs[:limite] if limite else qs
