"""Monetary policy of the system.

Rules (see docs/reglas_financieras.md):

* Every monetary amount is a ``Decimal``, never a ``float``.
* The smallest unit is one cent (2 decimal places).
* Rounding is ROUND_HALF_UP everywhere: interest, installments, balances
  and reports all use the same rule.
* When a total is split into installments, rounding differences are
  absorbed by the LAST installment, so the installments always add up to
  exactly the contractual total.
"""
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def to_decimal(value) -> Decimal:
    """Convert a value to Decimal without going through float."""
    if isinstance(value, Decimal):
        return value
    if value is None:
        return ZERO
    return Decimal(str(value))


def money(value) -> Decimal:
    """Round an amount to the monetary unit (2 decimals, HALF_UP)."""
    return to_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def split_into_installments(total, installment_count: int) -> list[Decimal]:
    """Split ``total`` into ``installment_count`` amounts.

    Every installment is equal except the last one, which absorbs the
    rounding difference so that ``sum(result) == money(total)`` exactly.
    """
    if installment_count < 1:
        raise ValueError("The number of installments must be 1 or greater.")
    total = money(total)
    base = money(total / Decimal(installment_count))
    installments = [base] * (installment_count - 1)
    installments.append(money(total - base * (installment_count - 1)))
    return installments


def distribute(amount, weights: list[Decimal]) -> list[Decimal]:
    """Split ``amount`` proportionally to ``weights``.

    The last element absorbs the rounding difference.
    """
    amount = money(amount)
    total_weight = sum(to_decimal(weight) for weight in weights)
    if total_weight <= ZERO:
        return [ZERO for _ in weights]
    result: list[Decimal] = []
    running_total = ZERO
    for weight in weights[:-1]:
        value = money(amount * to_decimal(weight) / total_weight)
        result.append(value)
        running_total += value
    result.append(money(amount - running_total))
    return result


def is_positive(value) -> bool:
    return to_decimal(value) > ZERO
