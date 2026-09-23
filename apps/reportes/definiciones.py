"""Catalogo de reportes.

Cada reporte declara sus columnas y una funcion que devuelve las filas a
partir del usuario (para respetar permisos) y de los filtros. Asi la vista,
la exportacion a CSV y la exportacion a Excel comparten exactamente los
mismos datos.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from django.db.models import Count, DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth

from apps.core.dinero import CERO, q
from apps.core.fechas import hoy_local
from apps.creditos.models import ESTADOS_DESEMBOLSADOS, Credito, Cuota, EstadoCuota
from apps.pagos.models import Pago
from apps.usuarios import permisos

DECIMAL = DecimalField(max_digits=14, decimal_places=2)
CERO_SQL = Value(CERO, output_field=DECIMAL)


@dataclass
class Reporte:
    clave: str
    nombre: str
    descripcion: str
    columnas: list[tuple[str, str]]
    generador: Callable
    filtros: list[str] = field(default_factory=lambda: ["negocio", "desde", "hasta"])


# --------------------------------------------------------------------------
# Utilidades de alcance
# --------------------------------------------------------------------------
def _creditos(usuario, filtros):
    qs = permisos.filtrar_por_negocio(Credito.objects.all(), usuario)
    qs = permisos.filtrar_cartera_cobrador(qs, usuario)
    if filtros.get("negocio"):
        qs = qs.filter(negocio=filtros["negocio"])
    if filtros.get("cobrador"):
        qs = qs.filter(cobrador=filtros["cobrador"])
    if filtros.get("estado"):
        qs = qs.filter(estado=filtros["estado"])
    return qs.select_related("cliente", "negocio", "cobrador")


def _pagos(usuario, filtros):
    qs = permisos.filtrar_por_negocio(Pago.objects.all(), usuario)
    qs = permisos.filtrar_cartera_cobrador(qs, usuario)
    if filtros.get("negocio"):
        qs = qs.filter(negocio=filtros["negocio"])
    if filtros.get("cobrador"):
        qs = qs.filter(cobrador=filtros["cobrador"])
    if filtros.get("metodo"):
        qs = qs.filter(metodo=filtros["metodo"])
    return qs.select_related("cliente", "credito", "negocio", "cobrador")


def _rango(qs, filtros, campo):
    if filtros.get("desde"):
        qs = qs.filter(**{f"{campo}__gte": filtros["desde"]})
    if filtros.get("hasta"):
        qs = qs.filter(**{f"{campo}__lte": filtros["hasta"]})
    return qs


# --------------------------------------------------------------------------
# Generadores
# --------------------------------------------------------------------------
def creditos_otorgados(usuario, filtros):
    qs = _rango(
        _creditos(usuario, filtros).filter(estado__in=ESTADOS_DESEMBOLSADOS),
        filtros, "fecha_desembolso")
    for credito in qs.order_by("-fecha_desembolso"):
        yield {
            "folio": credito.folio,
            "cliente": str(credito.cliente),
            "negocio": credito.negocio.nombre_comercial,
            "fecha_desembolso": credito.fecha_desembolso,
            "capital": credito.capital,
            "interes": credito.interes_total,
            "total": credito.total_a_pagar,
            "cuotas": credito.numero_cuotas,
            "frecuencia": credito.get_frecuencia_pago_display(),
            "estado": credito.get_estado_display(),
            "cobrador": str(credito.cobrador or "-"),
        }


def creditos_por_estado(usuario, filtros):
    qs = _creditos(usuario, filtros)
    filas = (
        qs.values("estado")
        .annotate(numero=Count("id"),
                  capital=Coalesce(Sum("capital"), CERO_SQL),
                  saldo=Coalesce(Sum("saldo_pendiente"), CERO_SQL))
        .order_by("estado")
    )
    from apps.creditos.models import EstadoCredito

    etiquetas = dict(EstadoCredito.choices)
    for fila in filas:
        yield {
            "estado": etiquetas.get(fila["estado"], fila["estado"]),
            "numero": fila["numero"],
            "capital": q(fila["capital"]),
            "saldo": q(fila["saldo"]),
        }


def creditos_por_negocio(usuario, filtros):
    qs = _rango(_creditos(usuario, filtros).filter(estado__in=ESTADOS_DESEMBOLSADOS),
                filtros, "fecha_desembolso")
    filas = (
        qs.values("negocio__nombre_comercial")
        .annotate(numero=Count("id"),
                  capital=Coalesce(Sum("capital"), CERO_SQL),
                  interes=Coalesce(Sum("interes_total"), CERO_SQL),
                  saldo=Coalesce(Sum("saldo_pendiente"), CERO_SQL))
        .order_by("-capital")
    )
    for fila in filas:
        yield {
            "negocio": fila["negocio__nombre_comercial"],
            "creditos": fila["numero"],
            "capital_colocado": q(fila["capital"]),
            "interes_contractual": q(fila["interes"]),
            "saldo_pendiente": q(fila["saldo"]),
        }


def pagos_periodo(usuario, filtros):
    qs = _rango(_pagos(usuario, filtros).confirmados(), filtros, "fecha__date")
    for pago in qs.order_by("-fecha"):
        yield {
            "folio": pago.folio,
            "fecha": pago.fecha.strftime("%d/%m/%Y %H:%M"),
            "cliente": str(pago.cliente),
            "credito": pago.credito.folio,
            "importe": pago.importe,
            "aplicado": pago.importe_aplicado,
            "excedente": pago.excedente,
            "metodo": pago.get_metodo_display(),
            "tipo": pago.get_tipo_display(),
            "cobrador": str(pago.cobrador or "-"),
            "recibido_por": str(pago.recibido_por),
        }


def flujo_efectivo(usuario, filtros):
    """Entradas de efectivo por mes (solo pagos reales, sin condonaciones)."""
    qs = _rango(_pagos(usuario, filtros).en_efectivo_real(), filtros, "fecha__date")
    filas = (
        qs.annotate(mes=TruncMonth("fecha"))
        .values("mes")
        .annotate(total=Coalesce(Sum("importe"), CERO_SQL), numero=Count("id"))
        .order_by("mes")
    )
    for fila in filas:
        yield {
            "mes": fila["mes"].strftime("%m/%Y") if fila["mes"] else "-",
            "numero_pagos": fila["numero"],
            "total_recibido": q(fila["total"]),
        }


def cartera_vigente_vencida(usuario, filtros):
    hoy = hoy_local()
    qs = _creditos(usuario, filtros).vigentes()
    for credito in qs.order_by("cliente__apellido_paterno"):
        vencido = credito.saldo_vencido
        yield {
            "folio": credito.folio,
            "cliente": str(credito.cliente),
            "negocio": credito.negocio.nombre_comercial,
            "saldo_total": credito.saldo_pendiente,
            "saldo_vencido": vencido,
            "saldo_por_vencer": q(credito.saldo_pendiente - vencido),
            "dias_atraso": credito.dias_atraso,
            "estado": credito.get_estado_display(),
            "corte": hoy.strftime("%d/%m/%Y"),
        }


def saldos_por_cliente(usuario, filtros):
    qs = _creditos(usuario, filtros).vigentes()
    filas = (
        qs.values("cliente_id", "cliente__nombres", "cliente__apellido_paterno",
                  "cliente__apellido_materno", "cliente__telefono_principal")
        .annotate(creditos=Count("id"),
                  saldo=Coalesce(Sum("saldo_pendiente"), CERO_SQL),
                  capital=Coalesce(Sum("capital"), CERO_SQL))
        .order_by("-saldo")
    )
    for fila in filas:
        nombre = " ".join(filter(None, [
            fila["cliente__nombres"], fila["cliente__apellido_paterno"],
            fila["cliente__apellido_materno"]]))
        yield {
            "cliente": nombre,
            "telefono": fila["cliente__telefono_principal"],
            "creditos_vigentes": fila["creditos"],
            "capital_prestado": q(fila["capital"]),
            "saldo_pendiente": q(fila["saldo"]),
        }


def intereses(usuario, filtros):
    qs = _rango(_creditos(usuario, filtros).filter(estado__in=ESTADOS_DESEMBOLSADOS),
                filtros, "fecha_desembolso")
    filas = qs.aggregate(
        contractual=Coalesce(Sum("interes_total"), CERO_SQL),
        cobrado=Coalesce(Sum("interes_pagado"), CERO_SQL),
        capital=Coalesce(Sum("capital"), CERO_SQL),
        capital_recuperado=Coalesce(Sum("capital_pagado"), CERO_SQL),
    )
    yield {
        "capital_colocado": q(filas["capital"]),
        "capital_recuperado": q(filas["capital_recuperado"]),
        "interes_contractual": q(filas["contractual"]),
        "interes_cobrado": q(filas["cobrado"]),
        "interes_pendiente": q(filas["contractual"] - filas["cobrado"]),
    }


def recuperacion_capital(usuario, filtros):
    qs = _rango(_creditos(usuario, filtros).filter(estado__in=ESTADOS_DESEMBOLSADOS),
                filtros, "fecha_desembolso")
    for credito in qs.order_by("-fecha_desembolso"):
        yield {
            "folio": credito.folio,
            "cliente": str(credito.cliente),
            "capital": credito.capital,
            "capital_recuperado": credito.capital_pagado,
            "interes_cobrado": credito.interes_pagado,
            "saldo_pendiente": credito.saldo_pendiente,
            "porcentaje_pagado": credito.porcentaje_pagado,
        }


def desempeno_cobrador(usuario, filtros):
    from apps.dashboard.servicios import desempeno_cobradores

    for fila in desempeno_cobradores(
        usuario, filtros.get("negocio"), filtros.get("desde"), filtros.get("hasta")
    ):
        yield {
            "cobrador": str(fila["cobrador"]),
            "pagos_recibidos": fila["pagos_recibidos"],
            "numero_pagos": fila["pagos_numero"],
            "cartera_asignada": fila["cartera_asignada"],
            "creditos_asignados": fila["creditos_asignados"],
            "saldo_vencido": fila["saldo_vencido"],
            "gestiones": fila["gestiones"],
            "promesas": fila["promesas"],
            "promesas_cumplidas": fila["promesas_cumplidas"],
        }


def historial_pagos(usuario, filtros):
    qs = _rango(_pagos(usuario, filtros), filtros, "fecha__date")
    for pago in qs.order_by("cliente__apellido_paterno", "-fecha"):
        yield {
            "cliente": str(pago.cliente),
            "credito": pago.credito.folio,
            "folio_pago": pago.folio,
            "fecha": pago.fecha.strftime("%d/%m/%Y"),
            "importe": pago.importe,
            "estado": pago.get_estado_display(),
            "metodo": pago.get_metodo_display(),
        }


def atrasos_recurrentes(usuario, filtros):
    """Creditos con mas cuotas que se pagaron tarde o siguen vencidas."""
    qs = _creditos(usuario, filtros)
    hoy = hoy_local()
    filas = (
        Cuota.objects.filter(credito__in=qs)
        .filter(fecha_vencimiento__lt=hoy)
        .exclude(estado=EstadoCuota.PAGADA)
        .values("credito_id")
        .annotate(vencidas=Count("id"),
                  saldo=Coalesce(Sum(F("importe_programado") - F("importe_pagado"),
                                     output_field=DECIMAL), CERO_SQL))
        .filter(vencidas__gte=filtros.get("minimo_atrasos") or 1)
        .order_by("-vencidas")
    )
    indice = {fila["credito_id"]: fila for fila in filas}
    for credito in qs.filter(pk__in=indice.keys()):
        fila = indice[credito.pk]
        yield {
            "folio": credito.folio,
            "cliente": str(credito.cliente),
            "telefono": credito.cliente.telefono_principal,
            "cuotas_vencidas": fila["vencidas"],
            "saldo_vencido": q(fila["saldo"]),
            "dias_atraso": credito.dias_atraso,
            "cobrador": str(credito.cobrador or "-"),
        }


def mayor_volumen(usuario, filtros):
    qs = _rango(_creditos(usuario, filtros).filter(estado__in=ESTADOS_DESEMBOLSADOS),
                filtros, "fecha_desembolso")
    filas = (
        qs.values("cliente__nombres", "cliente__apellido_paterno",
                  "cliente__apellido_materno")
        .annotate(numero=Count("id"), capital=Coalesce(Sum("capital"), CERO_SQL),
                  pagado=Coalesce(Sum("capital_pagado"), CERO_SQL))
        .order_by("-capital")[:100]
    )
    for fila in filas:
        nombre = " ".join(filter(None, [
            fila["cliente__nombres"], fila["cliente__apellido_paterno"],
            fila["cliente__apellido_materno"]]))
        yield {
            "cliente": nombre,
            "creditos": fila["numero"],
            "capital_historico": q(fila["capital"]),
            "capital_recuperado": q(fila["pagado"]),
        }


REPORTES: dict[str, Reporte] = {
    r.clave: r for r in [
        Reporte("creditos_otorgados", "Creditos otorgados por periodo",
                "Creditos desembolsados en el rango de fechas.",
                [("folio", "Folio"), ("cliente", "Cliente"), ("negocio", "Negocio"),
                 ("fecha_desembolso", "Desembolso"), ("capital", "Capital"),
                 ("interes", "Interes"), ("total", "Total"), ("cuotas", "Cuotas"),
                 ("frecuencia", "Frecuencia"), ("estado", "Estado"),
                 ("cobrador", "Cobrador")],
                creditos_otorgados),
        Reporte("creditos_estado", "Creditos activos y liquidados",
                "Conteo y saldos por estado del credito.",
                [("estado", "Estado"), ("numero", "Creditos"),
                 ("capital", "Capital"), ("saldo", "Saldo pendiente")],
                creditos_por_estado),
        Reporte("creditos_negocio", "Creditos por negocio o sucursal",
                "Colocacion y saldo agrupados por negocio.",
                [("negocio", "Negocio"), ("creditos", "Creditos"),
                 ("capital_colocado", "Capital colocado"),
                 ("interes_contractual", "Interes contractual"),
                 ("saldo_pendiente", "Saldo pendiente")],
                creditos_por_negocio),
        Reporte("pagos", "Pagos del periodo",
                "Detalle de pagos confirmados (diario, semanal o mensual segun el rango).",
                [("folio", "Folio"), ("fecha", "Fecha"), ("cliente", "Cliente"),
                 ("credito", "Credito"), ("importe", "Importe"),
                 ("aplicado", "Aplicado"), ("excedente", "Excedente"),
                 ("metodo", "Metodo"), ("tipo", "Tipo"), ("cobrador", "Cobrador"),
                 ("recibido_por", "Registrado por")],
                pagos_periodo),
        Reporte("flujo_efectivo", "Flujo de entradas de efectivo",
                "Dinero recibido por mes. No incluye condonaciones.",
                [("mes", "Mes"), ("numero_pagos", "Pagos"),
                 ("total_recibido", "Total recibido")],
                flujo_efectivo),
        Reporte("cartera", "Cartera vigente y vencida",
                "Saldo total, vencido y por vencer de cada credito vigente.",
                [("folio", "Folio"), ("cliente", "Cliente"), ("negocio", "Negocio"),
                 ("saldo_total", "Saldo total"), ("saldo_vencido", "Saldo vencido"),
                 ("saldo_por_vencer", "Por vencer"), ("dias_atraso", "Dias de atraso"),
                 ("estado", "Estado"), ("corte", "Fecha de corte")],
                cartera_vigente_vencida),
        Reporte("saldos_cliente", "Saldos pendientes por cliente",
                "Cuanto debe cada cliente en total.",
                [("cliente", "Cliente"), ("telefono", "Telefono"),
                 ("creditos_vigentes", "Creditos vigentes"),
                 ("capital_prestado", "Capital prestado"),
                 ("saldo_pendiente", "Saldo pendiente")],
                saldos_por_cliente),
        Reporte("intereses", "Intereses contractuales y cobrados",
                "Comparacion entre lo pactado y lo efectivamente cobrado.",
                [("capital_colocado", "Capital colocado"),
                 ("capital_recuperado", "Capital recuperado"),
                 ("interes_contractual", "Interes contractual"),
                 ("interes_cobrado", "Interes cobrado"),
                 ("interes_pendiente", "Interes pendiente")],
                intereses),
        Reporte("recuperacion", "Recuperacion de capital",
                "Avance de recuperacion credito por credito.",
                [("folio", "Folio"), ("cliente", "Cliente"), ("capital", "Capital"),
                 ("capital_recuperado", "Capital recuperado"),
                 ("interes_cobrado", "Interes cobrado"),
                 ("saldo_pendiente", "Saldo pendiente"),
                 ("porcentaje_pagado", "% pagado")],
                recuperacion_capital),
        Reporte("cobradores", "Desempeno por cobrador",
                "Pagos recibidos, cartera asignada y gestiones. El monto recibido "
                "NO es utilidad del negocio.",
                [("cobrador", "Cobrador"), ("pagos_recibidos", "Pagos recibidos"),
                 ("numero_pagos", "No. de pagos"),
                 ("cartera_asignada", "Cartera asignada"),
                 ("creditos_asignados", "Creditos"),
                 ("saldo_vencido", "Saldo vencido"), ("gestiones", "Gestiones"),
                 ("promesas", "Promesas"), ("promesas_cumplidas", "Cumplidas")],
                desempeno_cobrador),
        Reporte("historial_pagos", "Historial de pagos",
                "Todos los pagos, incluidos los reversados, ordenados por cliente.",
                [("cliente", "Cliente"), ("credito", "Credito"),
                 ("folio_pago", "Folio del pago"), ("fecha", "Fecha"),
                 ("importe", "Importe"), ("estado", "Estado"), ("metodo", "Metodo")],
                historial_pagos),
        Reporte("atrasos", "Creditos con atrasos recurrentes",
                "Creditos con cuotas vencidas sin pagar.",
                [("folio", "Folio"), ("cliente", "Cliente"), ("telefono", "Telefono"),
                 ("cuotas_vencidas", "Cuotas vencidas"),
                 ("saldo_vencido", "Saldo vencido"), ("dias_atraso", "Dias de atraso"),
                 ("cobrador", "Cobrador")],
                atrasos_recurrentes),
        Reporte("volumen", "Clientes con mayor volumen de credito",
                "Ranking por capital historico desembolsado.",
                [("cliente", "Cliente"), ("creditos", "Creditos"),
                 ("capital_historico", "Capital historico"),
                 ("capital_recuperado", "Capital recuperado")],
                mayor_volumen),
    ]
}
