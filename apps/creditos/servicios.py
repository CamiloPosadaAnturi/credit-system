"""Capa de servicios del ciclo de vida del credito.

Toda operacion que cambie dinero o estado pasa por aqui: las vistas no
calculan intereses ni saldos por su cuenta.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.auditoria.models import TipoAccion
from apps.auditoria.servicios import registrar
from apps.core.dinero import CERO, a_decimal, q
from apps.core.errores import ErrorDeCredito
from apps.core.fechas import hoy_local
from apps.creditos.calculos import (
    calcular_interes,
    calcular_total_a_pagar,
    construir_calendario,
)
from apps.creditos.models import (
    ESTADOS_EDITABLES,
    ESTADOS_VIGENTES,
    Credito,
    Cuota,
    EstadoCredito,
    EstadoCuota,
)


# --------------------------------------------------------------------------
# Folios
# --------------------------------------------------------------------------
def generar_folio(negocio) -> str:
    """Folio unico por negocio y anio: ``CR-<negocio>-<anio>-<consecutivo>``.

    Se genera dentro de la transaccion del llamador; la unicidad final la
    garantiza la restriccion UNIQUE de la base de datos.
    """
    anio = hoy_local().year
    prefijo = f"CR-{negocio.pk:03d}-{anio}-"
    ultimo = (
        Credito.objects.filter(folio__startswith=prefijo)
        .order_by("-folio")
        .values_list("folio", flat=True)
        .first()
    )
    consecutivo = int(ultimo.split("-")[-1]) + 1 if ultimo else 1
    return f"{prefijo}{consecutivo:05d}"


# --------------------------------------------------------------------------
# Alta y condiciones
# --------------------------------------------------------------------------
@transaction.atomic
def crear_credito(
    *,
    cliente,
    negocio,
    capital,
    numero_cuotas: int,
    frecuencia: str,
    fecha_primer_pago: dt.date,
    usuario=None,
    cobrador=None,
    modalidad_interes: str | None = None,
    tasa_interes=None,
    periodo_tasa: str | None = None,
    dias_personalizados: int | None = None,
    fecha_solicitud: dt.date | None = None,
    observaciones: str = "",
    estado: str = EstadoCredito.PENDIENTE,
) -> Credito:
    """Crea un credito con su calendario de pagos.

    La regla de interes se copia del negocio salvo que se indique otra.
    """
    if cliente.negocio_id != negocio.pk:
        raise ErrorDeCredito("El cliente no pertenece al negocio seleccionado.")
    capital = a_decimal(capital)
    if capital <= CERO:
        raise ErrorDeCredito("El capital debe ser mayor que cero.")

    regla = negocio.regla_interes_actual()
    modalidad = modalidad_interes or regla["modalidad_interes"]
    tasa = a_decimal(tasa_interes if tasa_interes is not None else regla["tasa_interes"])
    periodo = periodo_tasa or regla["periodo_tasa"]

    interes = calcular_interes(capital, modalidad, tasa, numero_cuotas)
    total = calcular_total_a_pagar(capital, interes)

    credito = Credito(
        folio=generar_folio(negocio),
        cliente=cliente,
        negocio=negocio,
        cobrador=cobrador or cliente.cobrador,
        fecha_solicitud=fecha_solicitud or hoy_local(),
        capital=q(capital),
        modalidad_interes=modalidad,
        tasa_interes=tasa,
        periodo_tasa=periodo,
        interes_total=interes,
        total_a_pagar=total,
        frecuencia_pago=frecuencia,
        dias_personalizados=dias_personalizados,
        numero_cuotas=numero_cuotas,
        fecha_primer_pago=fecha_primer_pago,
        saldo_pendiente=total,
        estado=estado,
        observaciones=observaciones,
        creado_por=usuario,
        actualizado_por=usuario,
    )
    credito.save()
    generar_calendario(credito)
    registrar(
        TipoAccion.CREAR,
        f"Credito {credito.folio} creado para {cliente} por {q(capital)} MXN",
        objeto=credito, usuario=usuario, negocio=negocio,
        datos={"capital": str(credito.capital), "interes": str(interes),
               "total": str(total), "cuotas": numero_cuotas},
    )
    return credito


@transaction.atomic
def recalcular_condiciones(credito: Credito, usuario=None) -> Credito:
    """Recalcula interes, total y calendario tras editar un credito editable."""
    if credito.estado not in ESTADOS_EDITABLES:
        raise ErrorDeCredito(
            "Un credito aprobado o desembolsado no puede recalcularse libremente. "
            "Usa una reestructuracion autorizada."
        )
    credito.interes_total = calcular_interes(
        credito.capital, credito.modalidad_interes, credito.tasa_interes,
        credito.numero_cuotas,
    )
    credito.total_a_pagar = calcular_total_a_pagar(credito.capital, credito.interes_total)
    credito.saldo_pendiente = credito.total_a_pagar
    credito.actualizado_por = usuario
    credito.save()
    generar_calendario(credito)
    return credito


@transaction.atomic
def generar_calendario(credito: Credito) -> list[Cuota]:
    """(Re)genera el calendario de cuotas de un credito sin pagos aplicados."""
    if credito.cuotas.filter(importe_pagado__gt=0).exists():
        raise ErrorDeCredito(
            "No se puede regenerar el calendario: el credito ya tiene pagos aplicados."
        )
    credito.cuotas.all().delete()
    filas = construir_calendario(
        credito.capital, credito.interes_total, credito.numero_cuotas,
        credito.fecha_primer_pago, credito.frecuencia_pago,
        credito.dias_personalizados,
    )
    cuotas = Cuota.objects.bulk_create([Cuota(credito=credito, **fila) for fila in filas])
    credito.importe_cuota = filas[0]["importe_programado"]
    credito.fecha_vencimiento_final = filas[-1]["fecha_vencimiento"]
    credito.save(update_fields=["importe_cuota", "fecha_vencimiento_final",
                                "actualizado_en"])
    return cuotas


# --------------------------------------------------------------------------
# Transiciones de estado
# --------------------------------------------------------------------------
@transaction.atomic
def aprobar_credito(credito: Credito, usuario, fecha: dt.date | None = None) -> Credito:
    credito = Credito.objects.select_for_update().get(pk=credito.pk)
    if credito.estado not in ESTADOS_EDITABLES:
        raise ErrorDeCredito(
            f"Solo se puede aprobar un credito en borrador o pendiente "
            f"(estado actual: {credito.get_estado_display()})."
        )
    if credito.cliente.esta_restringido:
        raise ErrorDeCredito(
            "El cliente esta restringido. Revisa su historial antes de aprobar."
        )
    # La regla de interes queda congelada en este momento.
    credito.interes_total = calcular_interes(
        credito.capital, credito.modalidad_interes, credito.tasa_interes,
        credito.numero_cuotas,
    )
    credito.total_a_pagar = calcular_total_a_pagar(credito.capital, credito.interes_total)
    credito.saldo_pendiente = credito.total_a_pagar
    credito.fecha_aprobacion = fecha or hoy_local()
    credito.aprobado_por = usuario
    credito.actualizado_por = usuario
    credito.estado = EstadoCredito.APROBADO
    credito.save()
    generar_calendario(credito)
    registrar(
        TipoAccion.APROBAR,
        f"Credito {credito.folio} aprobado (total {credito.total_a_pagar} MXN)",
        objeto=credito, usuario=usuario,
        datos={"tasa": str(credito.tasa_interes),
               "modalidad": credito.modalidad_interes,
               "interes": str(credito.interes_total)},
    )
    return credito


@transaction.atomic
def desembolsar_credito(credito: Credito, usuario, fecha: dt.date | None = None) -> Credito:
    credito = Credito.objects.select_for_update().get(pk=credito.pk)
    if credito.estado != EstadoCredito.APROBADO:
        raise ErrorDeCredito("Solo se puede desembolsar un credito aprobado.")
    credito.fecha_desembolso = fecha or hoy_local()
    credito.desembolsado_por = usuario
    credito.actualizado_por = usuario
    credito.estado = EstadoCredito.DESEMBOLSADO
    credito.save()
    actualizar_estado(credito)
    registrar(
        TipoAccion.DESEMBOLSAR,
        f"Credito {credito.folio} desembolsado por {credito.capital} MXN",
        objeto=credito, usuario=usuario,
        datos={"fecha_desembolso": str(credito.fecha_desembolso)},
    )
    return credito


@transaction.atomic
def cancelar_credito(credito: Credito, usuario, motivo: str) -> Credito:
    credito = Credito.objects.select_for_update().get(pk=credito.pk)
    if credito.estado == EstadoCredito.LIQUIDADO:
        raise ErrorDeCredito("Un credito liquidado no se puede cancelar.")
    if credito.total_pagado > CERO:
        raise ErrorDeCredito(
            "El credito tiene pagos aplicados. Reversa los pagos antes de cancelar "
            "o registra una reestructuracion."
        )
    if not motivo:
        raise ErrorDeCredito("Debes indicar el motivo de la cancelacion.")
    credito.estado = EstadoCredito.CANCELADO
    credito.motivo_cancelacion = motivo
    credito.saldo_pendiente = CERO
    credito.actualizado_por = usuario
    credito.save()
    credito.cuotas.update(estado=EstadoCuota.PENDIENTE)
    registrar(
        TipoAccion.CANCELAR, f"Credito {credito.folio} cancelado: {motivo}",
        objeto=credito, usuario=usuario,
    )
    return credito


@transaction.atomic
def reestructurar_credito(
    credito: Credito,
    usuario,
    *,
    numero_cuotas: int,
    frecuencia: str,
    fecha_primer_pago: dt.date,
    modalidad_interes: str | None = None,
    tasa_interes=None,
    observaciones: str = "",
) -> Credito:
    """Cierra el credito actual y crea uno nuevo por el saldo pendiente.

    El historial del credito original se conserva intacto: queda en estado
    ``reestructurado`` y el nuevo credito lo referencia.
    """
    credito = Credito.objects.select_for_update().get(pk=credito.pk)
    if credito.estado not in ESTADOS_VIGENTES:
        raise ErrorDeCredito("Solo se reestructura un credito vigente.")
    saldo = q(credito.saldo_pendiente)
    if saldo <= CERO:
        raise ErrorDeCredito("El credito no tiene saldo pendiente que reestructurar.")

    nuevo = crear_credito(
        cliente=credito.cliente,
        negocio=credito.negocio,
        capital=saldo,
        numero_cuotas=numero_cuotas,
        frecuencia=frecuencia,
        fecha_primer_pago=fecha_primer_pago,
        usuario=usuario,
        cobrador=credito.cobrador,
        modalidad_interes=modalidad_interes or credito.modalidad_interes,
        tasa_interes=tasa_interes if tasa_interes is not None else credito.tasa_interes,
        periodo_tasa=credito.periodo_tasa,
        observaciones=observaciones or f"Reestructuracion de {credito.folio}",
        estado=EstadoCredito.APROBADO,
    )
    nuevo.credito_origen = credito
    nuevo.fecha_aprobacion = hoy_local()
    nuevo.aprobado_por = usuario
    nuevo.save(update_fields=["credito_origen", "fecha_aprobacion", "aprobado_por"])
    desembolsar_credito(nuevo, usuario)
    nuevo.refresh_from_db()

    credito.estado = EstadoCredito.REESTRUCTURADO
    credito.saldo_pendiente = CERO
    credito.actualizado_por = usuario
    credito.save(update_fields=["estado", "saldo_pendiente", "actualizado_por",
                                "actualizado_en"])
    registrar(
        TipoAccion.REESTRUCTURAR,
        f"Credito {credito.folio} reestructurado en {nuevo.folio} por {saldo} MXN",
        objeto=credito, usuario=usuario,
        datos={"saldo_reestructurado": str(saldo), "nuevo_folio": nuevo.folio},
    )
    return nuevo


# --------------------------------------------------------------------------
# Saldos y estados derivados
# --------------------------------------------------------------------------
@transaction.atomic
def recalcular_credito(credito: Credito) -> Credito:
    """Reconstruye cuotas y saldos desde las aplicaciones de pago confirmadas.

    Esta funcion es la garantia de consistencia del sistema: el saldo nunca
    depende de sumas acumuladas 'a mano', siempre se puede recomputar.
    """
    from apps.pagos.models import AplicacionPago, EstadoPago

    aplicaciones = (
        AplicacionPago.objects.filter(
            cuota__credito=credito, pago__estado=EstadoPago.CONFIRMADO
        )
        .values("cuota_id")
        .annotate(
            importe=Sum("importe"),
            capital=Sum("capital"),
            interes=Sum("interes"),
        )
    )
    por_cuota = {fila["cuota_id"]: fila for fila in aplicaciones}

    total_capital = CERO
    total_interes = CERO
    hoy = hoy_local()
    for cuota in credito.cuotas.all():
        fila = por_cuota.get(cuota.pk)
        cuota.importe_pagado = q(fila["importe"]) if fila else CERO
        cuota.capital_pagado = q(fila["capital"]) if fila else CERO
        cuota.interes_pagado = q(fila["interes"]) if fila else CERO
        total_capital += cuota.capital_pagado
        total_interes += cuota.interes_pagado
        cuota.estado = _estado_cuota(cuota, hoy)
        if cuota.estado != EstadoCuota.PAGADA:
            cuota.fecha_liquidacion = None
        elif cuota.fecha_liquidacion is None:
            cuota.fecha_liquidacion = hoy
        cuota.save(update_fields=["importe_pagado", "capital_pagado", "interes_pagado",
                                   "estado", "fecha_liquidacion"])

    credito.capital_pagado = q(total_capital)
    credito.interes_pagado = q(total_interes)
    credito.saldo_pendiente = max(
        q(credito.total_a_pagar - total_capital - total_interes), CERO
    )
    credito.save(update_fields=["capital_pagado", "interes_pagado", "saldo_pendiente",
                                "actualizado_en"])
    actualizar_estado(credito)
    return credito


def _estado_cuota(cuota: Cuota, hoy: dt.date) -> str:
    if cuota.importe_pagado >= cuota.importe_programado:
        return EstadoCuota.PAGADA
    vencida = cuota.fecha_vencimiento < hoy
    if cuota.importe_pagado > CERO:
        return EstadoCuota.VENCIDA if vencida else EstadoCuota.PARCIAL
    return EstadoCuota.VENCIDA if vencida else EstadoCuota.PENDIENTE


def actualizar_estado(credito: Credito) -> str:
    """Determina el estado operativo del credito a partir de sus cuotas.

    No toca creditos cancelados, reestructurados o aun no desembolsados.
    """
    if credito.estado in (EstadoCredito.CANCELADO, EstadoCredito.REESTRUCTURADO,
                          EstadoCredito.BORRADOR, EstadoCredito.PENDIENTE,
                          EstadoCredito.APROBADO):
        return credito.estado

    nuevo = EstadoCredito.ACTIVO
    if credito.saldo_pendiente <= CERO:
        nuevo = EstadoCredito.LIQUIDADO
    else:
        dias_gracia = credito.negocio.dias_gracia
        limite = hoy_local() - dt.timedelta(days=dias_gracia)
        hay_mora = (
            credito.cuotas.filter(fecha_vencimiento__lt=limite)
            .exclude(estado=EstadoCuota.PAGADA)
            .exists()
        )
        if hay_mora:
            nuevo = EstadoCredito.EN_MORA

    if nuevo != credito.estado:
        anterior = credito.estado
        credito.estado = nuevo
        credito.save(update_fields=["estado", "actualizado_en"])
        if nuevo == EstadoCredito.LIQUIDADO:
            registrar(
                TipoAccion.EDITAR,
                f"Credito {credito.folio} liquidado (estado anterior: {anterior})",
                objeto=credito,
            )
    return credito.estado


def actualizar_estados_masivo(queryset=None) -> int:
    """Recorre los creditos vigentes y refresca su estado (mora / liquidado)."""
    queryset = queryset if queryset is not None else Credito.objects.vigentes()
    actualizados = 0
    for credito in queryset.select_related("negocio"):
        anterior = credito.estado
        if actualizar_estado(credito) != anterior:
            actualizados += 1
    return actualizados


def resumen_para_nuevo_credito(cliente) -> dict:
    """Informacion que se muestra ANTES de otorgar un nuevo credito.

    No emite una aprobacion ni un rechazo automatico: son datos para que
    una persona decida.
    """
    from apps.clientes.servicios import resumen_cliente

    resumen = resumen_cliente(cliente)
    resumen["creditos_vigentes"] = list(
        cliente.creditos.vigentes().order_by("fecha_desembolso")
    )
    resumen["alertas"] = []
    if resumen["saldo_pendiente"] > CERO:
        resumen["alertas"].append(
            f"El cliente tiene {q(resumen['saldo_pendiente'])} MXN de saldo pendiente."
        )
    if resumen["cuotas_vencidas"]:
        resumen["alertas"].append(
            f"Tiene {resumen['cuotas_vencidas']} cuota(s) vencida(s) sin pagar."
        )
    if cliente.esta_restringido:
        resumen["alertas"].append("El cliente esta marcado como RESTRINGIDO.")
    return resumen


def interes_por_cada_mil(tasa) -> Decimal:
    """Utilidad de presentacion: cuanto interes corresponde a 1,000 MXN."""
    return q(a_decimal(tasa) * 1000)
