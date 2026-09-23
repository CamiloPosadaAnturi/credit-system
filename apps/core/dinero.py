"""Politica monetaria del sistema.

Reglas (ver docs/reglas_financieras.md):

* Todo importe monetario se representa con ``Decimal``, nunca con ``float``.
* La unidad minima es el centavo (2 decimales).
* El redondeo es ROUND_HALF_UP (medio hacia arriba), consistente en todo
  el sistema: calculo de intereses, cuotas, saldos y reportes.
* Al dividir un total en cuotas, las diferencias de redondeo se absorben
  en la ULTIMA cuota, de modo que la suma de las cuotas es exactamente
  igual al total contractual.
"""
from decimal import ROUND_HALF_UP, Decimal

CENTAVO = Decimal("0.01")
CERO = Decimal("0.00")


def a_decimal(valor) -> Decimal:
    """Convierte un valor a Decimal sin pasar por float."""
    if isinstance(valor, Decimal):
        return valor
    if valor is None:
        return CERO
    return Decimal(str(valor))


def q(valor) -> Decimal:
    """Redondea un importe a la unidad monetaria (2 decimales, HALF_UP)."""
    return a_decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def dividir_en_cuotas(total, numero_cuotas: int) -> list[Decimal]:
    """Divide ``total`` en ``numero_cuotas`` importes.

    Todas las cuotas son iguales salvo la ultima, que absorbe la diferencia
    de redondeo para que ``sum(resultado) == q(total)`` exactamente.
    """
    if numero_cuotas < 1:
        raise ValueError("El numero de cuotas debe ser mayor o igual a 1.")
    total = q(total)
    base = q(total / Decimal(numero_cuotas))
    cuotas = [base] * (numero_cuotas - 1)
    cuotas.append(q(total - base * (numero_cuotas - 1)))
    return cuotas


def prorratear(importe, partes: list[Decimal]) -> list[Decimal]:
    """Reparte ``importe`` proporcionalmente a ``partes``.

    El ultimo elemento absorbe la diferencia de redondeo.
    """
    importe = q(importe)
    total_partes = sum(a_decimal(p) for p in partes)
    if total_partes <= CERO:
        return [CERO for _ in partes]
    resultado: list[Decimal] = []
    acumulado = CERO
    for parte in partes[:-1]:
        valor = q(importe * a_decimal(parte) / total_partes)
        resultado.append(valor)
        acumulado += valor
    resultado.append(q(importe - acumulado))
    return resultado


def es_positivo(valor) -> bool:
    return a_decimal(valor) > CERO
