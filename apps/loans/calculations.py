"""Pure financial calculations (no database access).

These functions are the SINGLE source of truth for interest, the
contractual total and the installment schedule. Any view, command or
report that needs those numbers calls them instead of repeating a formula.

Everything works with ``Decimal`` and rounds according to the monetary
policy defined in ``apps.core.money``.
"""
import datetime as dt
from decimal import Decimal

from apps.core.choices import DAYS_PER_FREQUENCY, InterestMode, PaymentFrequency
from apps.core.dates import add_days, add_months
from apps.core.money import ZERO, money, split_into_installments, to_decimal


def calculate_interest(principal, mode: str, rate, installment_count: int = 1) -> Decimal:
    """TOTAL interest of the loan, computed once on the initial principal.

    * ``flat_on_principal``: interest = principal x rate.
      With a rate of 0.40 -> 400 MXN per 1,000 MXN lent.
    * ``simple_per_period``: interest = principal x rate x installments
      (simple interest, always on the initial principal; never compounded).
    * ``no_interest``: 0.
    """
    principal = to_decimal(principal)
    rate = to_decimal(rate)
    if principal <= ZERO:
        raise ValueError("The principal must be greater than zero.")
    if rate < ZERO:
        raise ValueError("The rate cannot be negative.")
    if mode == InterestMode.NO_INTEREST:
        return ZERO
    if mode == InterestMode.FLAT_ON_PRINCIPAL:
        return money(principal * rate)
    if mode == InterestMode.SIMPLE_PER_PERIOD:
        if installment_count < 1:
            raise ValueError("The number of installments must be 1 or greater.")
        return money(principal * rate * Decimal(installment_count))
    raise ValueError(f"Unknown interest mode: {mode}")


def calculate_total_payable(principal, interest) -> Decimal:
    return money(to_decimal(principal) + to_decimal(interest))


def due_dates(
    first_payment_date: dt.date,
    frequency: str,
    installment_count: int,
    custom_days: int | None = None,
) -> list[dt.date]:
    """Due date of every installment.

    The first installment falls on ``first_payment_date``; the rest are
    spaced by the frequency. The monthly frequency follows the calendar
    (2026-01-31 + 1 month = 2026-02-28).
    """
    if installment_count < 1:
        raise ValueError("The number of installments must be 1 or greater.")

    if frequency == PaymentFrequency.MONTHLY:
        return [add_months(first_payment_date, index) for index in range(installment_count)]

    if frequency == PaymentFrequency.CUSTOM:
        if not custom_days or custom_days < 1:
            raise ValueError(
                "The custom frequency requires the number of days between installments."
            )
        step = int(custom_days)
    else:
        try:
            step = DAYS_PER_FREQUENCY[frequency]
        except KeyError as error:
            raise ValueError(f"Unknown frequency: {frequency}") from error

    return [add_days(first_payment_date, step * index) for index in range(installment_count)]


def build_schedule(
    principal,
    total_interest,
    installment_count: int,
    first_payment_date: dt.date,
    frequency: str,
    custom_days: int | None = None,
) -> list[dict]:
    """Payment schedule: one row per installment.

    Principal and interest are split evenly across the installments; the
    LAST one absorbs the rounding differences, so that:

        sum(scheduled_principal) == principal
        sum(scheduled_interest)  == total_interest
        sum(scheduled_amount)    == principal + total_interest
    """
    principal = money(principal)
    total_interest = money(total_interest)
    principal_parts = split_into_installments(principal, installment_count)
    interest_parts = (
        split_into_installments(total_interest, installment_count)
        if total_interest > ZERO
        else [ZERO] * installment_count
    )
    dates = due_dates(first_payment_date, frequency, installment_count, custom_days)

    schedule = []
    for index in range(installment_count):
        principal_part = principal_parts[index]
        interest_part = interest_parts[index]
        schedule.append(
            {
                "number": index + 1,
                "due_date": dates[index],
                "scheduled_principal": principal_part,
                "scheduled_interest": interest_part,
                "scheduled_amount": money(principal_part + interest_part),
            }
        )
    return schedule


def simulate(
    principal,
    mode: str,
    rate,
    installment_count: int,
    first_payment_date: dt.date,
    frequency: str,
    custom_days: int | None = None,
) -> dict:
    """Full summary of the terms shown before a loan is confirmed."""
    interest = calculate_interest(principal, mode, rate, installment_count)
    total = calculate_total_payable(principal, interest)
    schedule = build_schedule(
        principal, interest, installment_count, first_payment_date, frequency,
        custom_days,
    )
    return {
        "principal": money(principal),
        "total_interest": interest,
        "total_payable": total,
        "installment_count": installment_count,
        "installment_amount": schedule[0]["scheduled_amount"],
        "last_installment_amount": schedule[-1]["scheduled_amount"],
        "first_payment_date": first_payment_date,
        "final_due_date": schedule[-1]["due_date"],
        "schedule": schedule,
    }
