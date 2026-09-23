"""Calculos financieros puros (sin base de datos).

Estas funciones son la UNICA fuente de verdad para el interes, el total
contractual y el calendario de cuotas. Cualquier vista, comando o reporte
que necesite estos numeros debe llamarlas en lugar de repetir la formula.

Todas trabajan con ``Decimal`` y redondean segun la politica monetaria
definida en ``apps.core.dinero``.
"""
import datetime as dt
from decimal import Decimal

from apps.core.dinero import CERO, a_decimal, dividir_en_cuotas, q
from apps.core.fechas import sumar_dias, sumar_meses
from apps.core.opciones import DIAS_POR_FRECUENCIA, FrecuenciaPago, ModalidadInteres


def calcular_interes(capital, modalidad: str, tasa, numero_cuotas: int = 1) -> Decimal:
    """Interes TOTAL del credito, calculado una sola vez sobre el capital inicial.

    * ``fijo_capital``: interes = capital x tasa.
      Con tasa 0.40 -> 400 MXN por cada 1,000 MXN prestados.
    * ``simple_periodo``: interes = capital x tasa x numero de cuotas
      (interes simple, siempre sobre el capital inicial; nunca compuesto).
    * ``sin_interes``: 0.
    """
    capital = a_decimal(capital)
    tasa = a_decimal(tasa)
    if capital <= CERO:
        raise ValueError("El capital debe ser mayor que cero.")
    if tasa < CERO:
        raise ValueError("La tasa no puede ser negativa.")
    if modalidad == ModalidadInteres.SIN_INTERES:
        return CERO
    if modalidad == ModalidadInteres.FIJO_CAPITAL:
        return q(capital * tasa)
    if modalidad == ModalidadInteres.SIMPLE_PERIODO:
        if numero_cuotas < 1:
            raise ValueError("El numero de cuotas debe ser mayor o igual a 1.")
        return q(capital * tasa * Decimal(numero_cuotas))
    raise ValueError(f"Modalidad de interes desconocida: {modalidad}")


def calcular_total_a_pagar(capital, interes) -> Decimal:
    return q(a_decimal(capital) + a_decimal(interes))


def fechas_de_vencimiento(
    fecha_primer_pago: dt.date,
    frecuencia: str,
    numero_cuotas: int,
    dias_personalizados: int | None = None,
) -> list[dt.date]:
    """Fechas de vencimiento de cada cuota.

    La primera cuota vence en ``fecha_primer_pago``; las siguientes se
    espacian segun la frecuencia. La frecuencia mensual respeta el
    calendario (31/01 + 1 mes = 28/02).
    """
    if numero_cuotas < 1:
        raise ValueError("El numero de cuotas debe ser mayor o igual a 1.")

    if frecuencia == FrecuenciaPago.MENSUAL:
        return [sumar_meses(fecha_primer_pago, i) for i in range(numero_cuotas)]

    if frecuencia == FrecuenciaPago.PERSONALIZADO:
        if not dias_personalizados or dias_personalizados < 1:
            raise ValueError(
                "La frecuencia personalizada requiere el numero de dias entre cuotas."
            )
        paso = int(dias_personalizados)
    else:
        try:
            paso = DIAS_POR_FRECUENCIA[frecuencia]
        except KeyError as exc:
            raise ValueError(f"Frecuencia desconocida: {frecuencia}") from exc

    return [sumar_dias(fecha_primer_pago, paso * i) for i in range(numero_cuotas)]


def construir_calendario(
    capital,
    interes_total,
    numero_cuotas: int,
    fecha_primer_pago: dt.date,
    frecuencia: str,
    dias_personalizados: int | None = None,
) -> list[dict]:
    """Calendario de pagos: una fila por cuota.

    El capital y el interes se reparten en partes iguales entre las cuotas;
    la ULTIMA cuota absorbe las diferencias de redondeo, de modo que:

        sum(capital_programado) == capital
        sum(interes_programado) == interes_total
        sum(importe_programado) == capital + interes_total
    """
    capital = q(capital)
    interes_total = q(interes_total)
    capitales = dividir_en_cuotas(capital, numero_cuotas)
    intereses = (
        dividir_en_cuotas(interes_total, numero_cuotas)
        if interes_total > CERO
        else [CERO] * numero_cuotas
    )
    fechas = fechas_de_vencimiento(
        fecha_primer_pago, frecuencia, numero_cuotas, dias_personalizados
    )

    calendario = []
    for indice in range(numero_cuotas):
        capital_cuota = capitales[indice]
        interes_cuota = intereses[indice]
        calendario.append(
            {
                "numero": indice + 1,
                "fecha_vencimiento": fechas[indice],
                "capital_programado": capital_cuota,
                "interes_programado": interes_cuota,
                "importe_programado": q(capital_cuota + interes_cuota),
            }
        )
    return calendario


def simular(
    capital,
    modalidad: str,
    tasa,
    numero_cuotas: int,
    fecha_primer_pago: dt.date,
    frecuencia: str,
    dias_personalizados: int | None = None,
) -> dict:
    """Resumen completo de las condiciones antes de confirmar un credito."""
    interes = calcular_interes(capital, modalidad, tasa, numero_cuotas)
    total = calcular_total_a_pagar(capital, interes)
    calendario = construir_calendario(
        capital, interes, numero_cuotas, fecha_primer_pago, frecuencia,
        dias_personalizados,
    )
    return {
        "capital": q(capital),
        "interes_total": interes,
        "total_a_pagar": total,
        "numero_cuotas": numero_cuotas,
        "importe_cuota": calendario[0]["importe_programado"],
        "importe_ultima_cuota": calendario[-1]["importe_programado"],
        "fecha_primer_pago": fecha_primer_pago,
        "fecha_vencimiento_final": calendario[-1]["fecha_vencimiento"],
        "calendario": calendario,
    }
