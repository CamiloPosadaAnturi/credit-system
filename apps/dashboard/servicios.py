"""Indicadores del dashboard.

Definiciones (importante para no mezclar conceptos):

* Capital colocado: capital de los creditos DESEMBOLSADOS en el periodo.
  Es dinero que salio del negocio, no un ingreso.
* Interes contractual: interes pactado de esos creditos. Se devenga segun
  el contrato; no es utilidad cobrada.
* Total recaudado: dinero efectivamente recibido en el periodo (pagos
  confirmados, sin contar condonaciones).
* Saldo pendiente: lo que falta por cobrar de los creditos vigentes.
* Saldo vencido: la parte del saldo pendiente cuya fecha ya paso.
* Porcentaje de recuperacion: recaudado / total contractual de los
  creditos desembolsados en el periodo.
* Porcentaje de cartera vencida: saldo vencido / saldo pendiente.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce, TruncDate

from apps.cobranza.servicios import (
    cuotas_proximas,
    cuotas_que_vencen,
    cuotas_vencidas,
    saldo_vencido_queryset,
)
from apps.core.dinero import CERO, q
from apps.core.fechas import hoy_local
from apps.creditos.models import ESTADOS_DESEMBOLSADOS, Credito, EstadoCredito
from apps.pagos.models import Pago
from apps.usuarios import permisos

DECIMAL = DecimalField(max_digits=14, decimal_places=2)


def _cero():
    return Value(Decimal("0"), output_field=DECIMAL)


def porcentaje(parte, total) -> Decimal:
    parte = parte or CERO
    total = total or CERO
    if total <= CERO:
        return CERO
    return q(Decimal(parte) * 100 / Decimal(total))


def alcance(usuario, negocio=None):
    """Creditos y pagos que el usuario puede ver, opcionalmente de un negocio."""
    creditos = permisos.filtrar_por_negocio(Credito.objects.all(), usuario)
    creditos = permisos.filtrar_cartera_cobrador(creditos, usuario)
    pagos = permisos.filtrar_por_negocio(Pago.objects.all(), usuario)
    pagos = permisos.filtrar_cartera_cobrador(pagos, usuario)
    if negocio:
        creditos = creditos.filter(negocio=negocio)
        pagos = pagos.filter(negocio=negocio)
    return creditos, pagos


def indicadores(usuario, negocio=None, desde: dt.date | None = None,
                hasta: dt.date | None = None) -> dict:
    creditos, pagos = alcance(usuario, negocio)
    hoy = hoy_local()
    desde = desde or hoy.replace(day=1)
    hasta = hasta or hoy

    desembolsados = creditos.filter(estado__in=ESTADOS_DESEMBOLSADOS)
    del_periodo = desembolsados.filter(
        fecha_desembolso__gte=desde, fecha_desembolso__lte=hasta)

    colocacion = del_periodo.aggregate(
        capital=Coalesce(Sum("capital"), _cero()),
        interes=Coalesce(Sum("interes_total"), _cero()),
        total=Coalesce(Sum("total_a_pagar"), _cero()),
        numero=Count("id"),
    )

    pagos_periodo = pagos.en_efectivo_real().filter(
        fecha__date__gte=desde, fecha__date__lte=hasta)
    recaudado = pagos_periodo.aggregate(t=Coalesce(Sum("importe"), _cero()))["t"]

    vigentes = creditos.vigentes()
    saldo_pendiente = vigentes.aggregate(
        t=Coalesce(Sum("saldo_pendiente"), _cero()))["t"]
    saldo_vencido = saldo_vencido_queryset(vigentes, hoy)

    pagos_hoy = pagos.en_efectivo_real().filter(fecha__date=hoy).aggregate(
        total=Coalesce(Sum("importe"), _cero()), numero=Count("id"))
    cuotas_hoy = cuotas_que_vencen(vigentes, hoy)
    programado_hoy = cuotas_hoy.aggregate(
        t=Coalesce(Sum(F("importe_programado") - F("importe_pagado"),
                       output_field=DECIMAL), _cero()))["t"]

    clientes_activos = (
        vigentes.values("cliente_id").distinct().count()
    )

    return {
        "desde": desde,
        "hasta": hasta,
        "capital_colocado": q(colocacion["capital"]),
        "interes_contractual": q(colocacion["interes"]),
        "total_contractual": q(colocacion["total"]),
        "creditos_otorgados": colocacion["numero"],
        "total_recaudado": q(recaudado),
        "saldo_pendiente": q(saldo_pendiente),
        "saldo_vencido": q(saldo_vencido),
        "creditos_activos": vigentes.count(),
        "creditos_liquidados": creditos.filter(
            estado=EstadoCredito.LIQUIDADO).count(),
        "creditos_en_mora": creditos.filter(estado=EstadoCredito.EN_MORA).count(),
        "clientes_activos": clientes_activos,
        "pagos_programados_hoy_num": cuotas_hoy.count(),
        "pagos_programados_hoy": q(programado_hoy),
        "pagos_recibidos_hoy": q(pagos_hoy["total"]),
        "pagos_recibidos_hoy_num": pagos_hoy["numero"],
        "cuotas_vencidas": cuotas_vencidas(vigentes, hoy).count(),
        "cuotas_proximas": cuotas_proximas(vigentes, 7, hoy).count(),
        "porcentaje_recuperacion": porcentaje(recaudado, colocacion["total"]),
        "porcentaje_cartera_vencida": porcentaje(saldo_vencido, saldo_pendiente),
    }


# --------------------------------------------------------------------------
# Secciones del dashboard
# --------------------------------------------------------------------------
def clientes_a_cobrar_hoy(usuario, negocio=None, fecha: dt.date | None = None):
    creditos, _ = alcance(usuario, negocio)
    return cuotas_que_vencen(creditos.vigentes(), fecha or hoy_local())


def clientes_en_mora(usuario, negocio=None):
    from apps.cobranza.servicios import resumen_mora_por_credito

    creditos, _ = alcance(usuario, negocio)
    return resumen_mora_por_credito(creditos.vigentes())


def ranking_solicitantes(usuario, negocio=None, desde=None, hasta=None, limite=10):
    """Clientes que mas credito han solicitado (monto y numero)."""
    creditos, _ = alcance(usuario, negocio)
    qs = creditos.filter(estado__in=ESTADOS_DESEMBOLSADOS)
    if desde:
        qs = qs.filter(fecha_desembolso__gte=desde)
    if hasta:
        qs = qs.filter(fecha_desembolso__lte=hasta)
    base = (
        qs.values("cliente_id", "cliente__nombres", "cliente__apellido_paterno",
                  "cliente__apellido_materno")
        .annotate(capital=Coalesce(Sum("capital"), _cero()), numero=Count("id"))
    )
    return {
        "por_monto": list(base.order_by("-capital")[:limite]),
        "por_numero": list(base.order_by("-numero", "-capital")[:limite]),
    }


def ranking_pagadores(usuario, negocio=None, desde=None, hasta=None, limite=10):
    """Clientes que mas han pagado: en el periodo y en toda su historia."""
    _, pagos = alcance(usuario, negocio)
    confirmados = pagos.en_efectivo_real()
    periodo = confirmados
    if desde:
        periodo = periodo.filter(fecha__date__gte=desde)
    if hasta:
        periodo = periodo.filter(fecha__date__lte=hasta)

    def agrupar(queryset):
        return list(
            queryset.values("cliente_id", "cliente__nombres",
                            "cliente__apellido_paterno", "cliente__apellido_materno")
            .annotate(total=Coalesce(Sum("importe"), _cero()), numero=Count("id"))
            .order_by("-total")[:limite]
        )

    return {"periodo": agrupar(periodo), "historico": agrupar(confirmados)}


def desempeno_cobradores(usuario, negocio=None, desde=None, hasta=None):
    """Indicadores por cobrador.

    ADVERTENCIA: el monto recibido por un cobrador NO es utilidad del
    negocio; es dinero cobrado que incluye capital e interes.
    """
    from apps.cobranza.models import GestionCobranza
    from apps.usuarios.models import Rol, Usuario

    creditos, pagos = alcance(usuario, negocio)
    negocios = permisos.negocios_permitidos(usuario)
    cobradores = Usuario.objects.filter(
        rol=Rol.COBRADOR, negocios__in=negocios).distinct()

    filas = []
    for cobrador in cobradores:
        pagos_cobrador = pagos.en_efectivo_real().filter(cobrador=cobrador)
        if desde:
            pagos_cobrador = pagos_cobrador.filter(fecha__date__gte=desde)
        if hasta:
            pagos_cobrador = pagos_cobrador.filter(fecha__date__lte=hasta)
        agregado = pagos_cobrador.aggregate(
            total=Coalesce(Sum("importe"), _cero()), numero=Count("id"))

        cartera = creditos.vigentes().filter(cobrador=cobrador)
        cartera_agregada = cartera.aggregate(
            saldo=Coalesce(Sum("saldo_pendiente"), _cero()), numero=Count("id"))

        gestiones = GestionCobranza.objects.filter(usuario=cobrador)
        if desde:
            gestiones = gestiones.filter(fecha__date__gte=desde)
        if hasta:
            gestiones = gestiones.filter(fecha__date__lte=hasta)
        promesas = gestiones.filter(monto_prometido__gt=0)
        cumplidas = sum(1 for gestion in promesas if gestion.promesa_cumplida)

        filas.append({
            "cobrador": cobrador,
            "pagos_recibidos": q(agregado["total"]),
            "pagos_numero": agregado["numero"],
            "cartera_asignada": q(cartera_agregada["saldo"]),
            "creditos_asignados": cartera_agregada["numero"],
            "gestiones": gestiones.count(),
            "promesas": promesas.count(),
            "promesas_cumplidas": cumplidas,
            "saldo_vencido": saldo_vencido_queryset(cartera),
        })
    filas.sort(key=lambda fila: fila["pagos_recibidos"], reverse=True)
    return filas


def actividad_reciente(usuario, negocio=None, limite=10) -> dict:
    from apps.clientes.models import Cliente

    creditos, pagos = alcance(usuario, negocio)
    clientes = permisos.filtrar_por_negocio(Cliente.objects.all(), usuario)
    if negocio:
        clientes = clientes.filter(negocio=negocio)
    return {
        "clientes_nuevos": clientes.order_by("-creado_en")[:limite],
        "creditos_nuevos": creditos.select_related("cliente").order_by("-creado_en")[:limite],
        "desembolsos": creditos.filter(fecha_desembolso__isnull=False)
        .select_related("cliente").order_by("-fecha_desembolso", "-id")[:limite],
        "pagos_recientes": pagos.confirmados().select_related("cliente", "credito")
        .order_by("-fecha")[:limite],
    }


def serie_pagos(usuario, negocio=None, dias: int = 30) -> dict:
    """Serie diaria de recaudacion para el grafico del dashboard."""
    _, pagos = alcance(usuario, negocio)
    hoy = hoy_local()
    inicio = hoy - dt.timedelta(days=dias - 1)
    filas = (
        pagos.en_efectivo_real()
        .filter(fecha__date__gte=inicio)
        .annotate(dia=TruncDate("fecha"))
        .values("dia")
        .annotate(total=Coalesce(Sum("importe"), _cero()))
        .order_by("dia")
    )
    indice = {fila["dia"]: fila["total"] for fila in filas}
    etiquetas, valores = [], []
    for indice_dia in range(dias):
        dia = inicio + dt.timedelta(days=indice_dia)
        etiquetas.append(dia.strftime("%d/%m"))
        valores.append(float(indice.get(dia, 0)))
    return {"etiquetas": etiquetas, "valores": valores}


def composicion_cartera(usuario, negocio=None) -> dict:
    """Distribucion de la cartera vigente por estado (grafico de dona)."""
    creditos, _ = alcance(usuario, negocio)
    filas = (
        creditos.values("estado")
        .annotate(numero=Count("id"), saldo=Coalesce(Sum("saldo_pendiente"), _cero()))
        .order_by("-numero")
    )
    etiquetas = [dict(EstadoCredito.choices).get(f["estado"], f["estado"]) for f in filas]
    return {
        "etiquetas": etiquetas,
        "numeros": [f["numero"] for f in filas],
        "saldos": [float(f["saldo"]) for f in filas],
    }


def pagos_vs_programado(usuario, negocio=None, dias: int = 14) -> dict:
    """Compara lo programado contra lo cobrado por dia."""
    from apps.creditos.models import Cuota

    creditos, pagos = alcance(usuario, negocio)
    hoy = hoy_local()
    inicio = hoy - dt.timedelta(days=dias - 1)

    programado = (
        Cuota.objects.filter(credito__in=creditos, fecha_vencimiento__gte=inicio,
                             fecha_vencimiento__lte=hoy)
        .values("fecha_vencimiento")
        .annotate(total=Coalesce(Sum("importe_programado"), _cero()))
    )
    indice_prog = {f["fecha_vencimiento"]: float(f["total"]) for f in programado}

    cobrado = (
        pagos.en_efectivo_real().filter(fecha__date__gte=inicio)
        .annotate(dia=TruncDate("fecha")).values("dia")
        .annotate(total=Coalesce(Sum("importe"), _cero()))
    )
    indice_cobrado = {f["dia"]: float(f["total"]) for f in cobrado}

    etiquetas, serie_prog, serie_cobrado = [], [], []
    for indice_dia in range(dias):
        dia = inicio + dt.timedelta(days=indice_dia)
        etiquetas.append(dia.strftime("%d/%m"))
        serie_prog.append(indice_prog.get(dia, 0.0))
        serie_cobrado.append(indice_cobrado.get(dia, 0.0))
    return {"etiquetas": etiquetas, "programado": serie_prog, "cobrado": serie_cobrado}


def creditos_por_estado(usuario, negocio=None):
    creditos, _ = alcance(usuario, negocio)
    return (
        creditos.values("estado")
        .annotate(numero=Count("id"), total=Coalesce(Sum("saldo_pendiente"), _cero()))
        .order_by("estado")
    )


