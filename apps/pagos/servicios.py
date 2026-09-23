"""Registro y aplicacion de pagos.

Politica de aplicacion (configurable, ver docs/reglas_financieras.md):

1. El pago se aplica primero a las cuotas VENCIDAS mas antiguas y despues
   a las siguientes por orden de vencimiento.
2. Dentro de cada cuota se cubre primero el INTERES programado y luego el
   CAPITAL. Esto no genera intereses nuevos: solo reparte lo ya pactado.
3. La distribucion se guarda en ``AplicacionPago``, de modo que el saldo
   siempre puede reconstruirse desde cero.

Todas las operaciones son atomicas y bloquean el credito
(``select_for_update``) para evitar inconsistencias por pagos simultaneos.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.auditoria.models import TipoAccion
from apps.auditoria.servicios import registrar
from apps.core.dinero import CERO, a_decimal, q
from apps.core.errores import ErrorDePago
from apps.creditos.models import ESTADOS_VIGENTES, Credito, Cuota, EstadoCuota
from apps.creditos.servicios import recalcular_credito
from apps.pagos.models import AplicacionPago, EstadoPago, MetodoPago, Pago, TipoPago

#: Segundos dentro de los cuales un pago identico se considera duplicado.
VENTANA_DUPLICADOS_SEG = 120


def generar_folio_pago(negocio) -> str:
    anio = timezone.localdate().year
    prefijo = f"PG-{negocio.pk:03d}-{anio}-"
    ultimo = (
        Pago.objects.filter(folio__startswith=prefijo)
        .order_by("-folio")
        .values_list("folio", flat=True)
        .first()
    )
    consecutivo = int(ultimo.split("-")[-1]) + 1 if ultimo else 1
    return f"{prefijo}{consecutivo:05d}"


def saldo_exigible(credito: Credito) -> Decimal:
    """Lo que el cliente debe por el contrato completo."""
    return q(credito.saldo_pendiente)


def saldo_vencido(credito: Credito, hoy: dt.date | None = None) -> Decimal:
    from apps.core.fechas import hoy_local

    hoy = hoy or hoy_local()
    total = CERO
    for cuota in credito.cuotas.filter(fecha_vencimiento__lt=hoy).exclude(
        estado=EstadoCuota.PAGADA
    ):
        total += cuota.saldo
    return q(total)


@transaction.atomic
def registrar_pago(
    *,
    credito: Credito,
    importe,
    usuario,
    metodo: str = MetodoPago.EFECTIVO,
    fecha=None,
    cobrador=None,
    referencia: str = "",
    observaciones: str = "",
    clave_idempotencia: str = "",
    permitir_excedente: bool = False,
    tipo: str = TipoPago.PAGO,
    forzar_duplicado: bool = False,
) -> Pago:
    """Registra un abono y lo aplica a las cuotas del credito."""
    importe = q(a_decimal(importe))
    if importe <= CERO:
        raise ErrorDePago("El importe del pago debe ser mayor que cero.")

    if clave_idempotencia:
        existente = Pago.objects.filter(clave_idempotencia=clave_idempotencia).first()
        if existente:
            # El formulario se envio dos veces: se devuelve el pago original.
            return existente

    credito = Credito.objects.select_for_update().get(pk=credito.pk)
    if credito.estado not in ESTADOS_VIGENTES:
        raise ErrorDePago(
            f"No se pueden registrar pagos en un credito {credito.get_estado_display()}."
        )

    fecha = fecha or timezone.now()
    if not forzar_duplicado:
        _validar_duplicado(credito, importe, fecha)

    exigible = saldo_exigible(credito)
    if importe > exigible and not permitir_excedente:
        raise ErrorDePago(
            f"El importe ({importe} MXN) supera el saldo exigible del credito "
            f"({exigible} MXN). Autoriza el excedente o registra una liquidacion."
        )

    pago = Pago.objects.create(
        folio=generar_folio_pago(credito.negocio),
        credito=credito,
        cliente=credito.cliente,
        negocio=credito.negocio,
        fecha=fecha,
        importe=importe,
        metodo=metodo,
        tipo=tipo,
        estado=EstadoPago.CONFIRMADO,
        recibido_por=usuario,
        cobrador=cobrador or credito.cobrador,
        referencia=referencia,
        observaciones=observaciones,
        clave_idempotencia=clave_idempotencia,
    )

    aplicado, excedente = aplicar_pago(pago, credito)
    pago.importe_aplicado = aplicado
    pago.excedente = excedente
    pago.save(update_fields=["importe_aplicado", "excedente"])

    recalcular_credito(credito)

    registrar(
        TipoAccion.PAGO,
        f"Pago {pago.folio} de {importe} MXN aplicado a {credito.folio}",
        objeto=pago, usuario=usuario, negocio=credito.negocio,
        datos={"credito": credito.folio, "importe": str(importe),
               "aplicado": str(aplicado), "excedente": str(excedente),
               "metodo": metodo, "tipo": tipo},
    )
    _notificar_liquidacion(credito)
    return pago


def _validar_duplicado(credito: Credito, importe: Decimal, fecha) -> None:
    limite = fecha - dt.timedelta(seconds=VENTANA_DUPLICADOS_SEG)
    duplicado = Pago.objects.filter(
        credito=credito, importe=importe, estado=EstadoPago.CONFIRMADO,
        fecha__gte=limite, fecha__lte=fecha,
    ).exists()
    if duplicado:
        raise ErrorDePago(
            "Ya existe un pago identico registrado hace menos de dos minutos. "
            "Si realmente son dos pagos distintos, marca la casilla de confirmacion."
        )


def aplicar_pago(pago: Pago, credito: Credito | None = None) -> tuple[Decimal, Decimal]:
    """Reparte el importe del pago entre las cuotas pendientes.

    Devuelve ``(importe_aplicado, excedente)``.
    """
    credito = credito or pago.credito
    remanente = q(pago.importe)
    aplicado = CERO

    cuotas = list(
        Cuota.objects.select_for_update()
        .filter(credito=credito)
        .exclude(estado=EstadoCuota.PAGADA)
        .order_by("fecha_vencimiento", "numero")
    )

    for cuota in cuotas:
        if remanente <= CERO:
            break
        saldo_cuota = q(cuota.saldo)
        if saldo_cuota <= CERO:
            continue
        a_aplicar = min(saldo_cuota, remanente)
        # Dentro de la cuota: primero interes, luego capital.
        interes = min(q(cuota.saldo_interes), a_aplicar)
        capital = q(a_aplicar - interes)
        AplicacionPago.objects.create(
            pago=pago, cuota=cuota, importe=a_aplicar,
            capital=capital, interes=interes,
        )
        remanente = q(remanente - a_aplicar)
        aplicado = q(aplicado + a_aplicar)

    return aplicado, q(remanente)


@transaction.atomic
def reversar_pago(pago: Pago, usuario, motivo: str) -> Pago:
    """Reversa un pago confirmado. El registro original NUNCA se elimina."""
    if not motivo:
        raise ErrorDePago("Debes indicar el motivo del reverso.")
    pago = Pago.objects.select_for_update().get(pk=pago.pk)
    if pago.estado != EstadoPago.CONFIRMADO:
        raise ErrorDePago("Solo se puede reversar un pago confirmado.")

    pago.estado = EstadoPago.REVERSADO
    pago.motivo_reverso = motivo
    pago.reversado_por = usuario
    pago.reversado_en = timezone.now()
    pago.save(update_fields=["estado", "motivo_reverso", "reversado_por", "reversado_en"])

    credito = Credito.objects.select_for_update().get(pk=pago.credito_id)
    # recalcular_credito recomputa el saldo desde las aplicaciones confirmadas
    # y devuelve el credito a 'activo' o 'en_mora' si vuelve a tener saldo.
    recalcular_credito(credito)

    registrar(
        TipoAccion.REVERSO,
        f"Pago {pago.folio} reversado ({pago.importe} MXN): {motivo}",
        objeto=pago, usuario=usuario, negocio=pago.negocio,
        datos={"credito": credito.folio, "importe": str(pago.importe), "motivo": motivo},
    )
    return pago


# --------------------------------------------------------------------------
# Liquidacion anticipada
# --------------------------------------------------------------------------
def calcular_liquidacion_anticipada(credito: Credito) -> dict:
    """Cuanto tendria que pagar hoy el cliente para liquidar el credito.

    Si el negocio configuro un descuento sobre el interes NO devengado
    (cuotas que aun no vencen), se aplica aqui. Con descuento 0 el cliente
    paga el saldo contractual completo.
    """
    from apps.core.fechas import hoy_local

    hoy = hoy_local()
    saldo = saldo_exigible(credito)
    interes_no_devengado = CERO
    for cuota in credito.cuotas.filter(fecha_vencimiento__gt=hoy).exclude(
        estado=EstadoCuota.PAGADA
    ):
        interes_no_devengado += cuota.saldo_interes

    tasa_descuento = a_decimal(credito.negocio.descuento_liquidacion_anticipada)
    descuento = q(interes_no_devengado * tasa_descuento)
    return {
        "saldo_contractual": saldo,
        "interes_no_devengado": q(interes_no_devengado),
        "tasa_descuento": tasa_descuento,
        "descuento": descuento,
        "importe_liquidacion": q(saldo - descuento),
        "permitida": credito.negocio.permite_liquidacion_anticipada,
    }


@transaction.atomic
def liquidar_anticipadamente(
    credito: Credito, usuario, *, metodo: str = MetodoPago.EFECTIVO,
    referencia: str = "", observaciones: str = "", clave_idempotencia: str = "",
) -> Pago:
    """Registra el pago de liquidacion y, si aplica, la condonacion autorizada."""
    calculo = calcular_liquidacion_anticipada(credito)
    if not calculo["permitida"]:
        raise ErrorDePago("Este negocio no permite la liquidacion anticipada.")
    if calculo["importe_liquidacion"] <= CERO:
        raise ErrorDePago("El credito no tiene saldo por liquidar.")

    pago = registrar_pago(
        credito=credito,
        importe=calculo["importe_liquidacion"],
        usuario=usuario,
        metodo=metodo,
        referencia=referencia,
        observaciones=observaciones or "Liquidacion anticipada",
        clave_idempotencia=clave_idempotencia,
        forzar_duplicado=True,
    )

    if calculo["descuento"] > CERO:
        registrar_pago(
            credito=credito,
            importe=calculo["descuento"],
            usuario=usuario,
            metodo=MetodoPago.OTRO,
            tipo=TipoPago.CONDONACION,
            observaciones=(
                f"Condonacion autorizada por liquidacion anticipada de "
                f"{credito.folio} (descuento sobre interes no devengado)"
            ),
            forzar_duplicado=True,
        )
    return pago


def _notificar_liquidacion(credito: Credito) -> None:
    from apps.creditos.models import EstadoCredito

    credito.refresh_from_db(fields=["estado"])
    if credito.estado == EstadoCredito.LIQUIDADO:
        from apps.notificaciones.servicios import crear_notificacion

        crear_notificacion(
            negocio=credito.negocio,
            titulo=f"Credito {credito.folio} liquidado",
            mensaje=f"{credito.cliente} liquido su credito de {credito.capital} MXN.",
            url=credito.get_absolute_url(),
        )
