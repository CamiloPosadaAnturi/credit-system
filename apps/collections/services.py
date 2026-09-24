"""Portfolio classification and past-due calculations.

Definitions (see docs/reglas_financieras.md):

* Days past due of an INSTALLMENT: calendar days between its due date and
  today, while it still has a balance.
* Days past due of a LOAN: those of its oldest overdue installment.
* Overdue balance: the sum of the balances of installments already due.
* Total outstanding balance: everything left to pay on the contract,
  whether due or not.

The system does NOT add automatic late fees: it only computes them when
the business has a configured and enabled policy.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Min, Q, Sum

from apps.core.dates import today_local
from apps.core.money import ZERO, money, to_decimal
from apps.loans.models import Installment, InstallmentStatus, Loan

INSTALLMENT_BALANCE = ExpressionWrapper(
    F("scheduled_amount") - F("amount_paid"),
    output_field=DecimalField(max_digits=12, decimal_places=2),
)


def installments_of(loans):
    return Installment.objects.filter(loan__in=loans)


def overdue_balance_for(loans, today: dt.date | None = None) -> Decimal:
    """Sum of the balances of the overdue installments of a set of loans."""
    today = today or today_local()
    total = (
        installments_of(loans)
        .filter(due_date__lt=today)
        .exclude(status=InstallmentStatus.PAID)
        .aggregate(total=Sum(INSTALLMENT_BALANCE))["total"]
    )
    return money(total or ZERO)


def installments_due_on(loans, date: dt.date | None = None):
    date = date or today_local()
    return (
        installments_of(loans)
        .filter(due_date=date)
        .exclude(status=InstallmentStatus.PAID)
        .select_related("loan", "loan__customer", "loan__collector")
        .order_by("loan__customer__last_name")
    )


def upcoming_installments(loans, days: int = 7, start: dt.date | None = None):
    start = start or today_local()
    end = start + dt.timedelta(days=days)
    return (
        installments_of(loans)
        .filter(due_date__gt=start, due_date__lte=end)
        .exclude(status=InstallmentStatus.PAID)
        .select_related("loan", "loan__customer", "loan__collector")
        .order_by("due_date")
    )


def overdue_installments(loans, today: dt.date | None = None, min_days: int = 0):
    today = today or today_local()
    cutoff = today - dt.timedelta(days=min_days)
    return (
        installments_of(loans)
        .filter(due_date__lt=cutoff)
        .exclude(status=InstallmentStatus.PAID)
        .select_related("loan", "loan__customer", "loan__collector")
        .order_by("due_date")
    )


def past_due_loans(loans, today: dt.date | None = None, grace_days: int = 0):
    today = today or today_local()
    cutoff = today - dt.timedelta(days=grace_days)
    return loans.filter(
        Q(installments__due_date__lt=cutoff)
        & ~Q(installments__status=InstallmentStatus.PAID)
    ).distinct()


def past_due_summary(loans, today: dt.date | None = None) -> list[dict]:
    """One row per loan with overdue installments: days, overdue and total balance."""
    today = today or today_local()
    rows = (
        installments_of(loans)
        .filter(due_date__lt=today)
        .exclude(status=InstallmentStatus.PAID)
        .values("loan_id")
        .annotate(
            overdue_count=Count("id"),
            overdue_balance=Sum(INSTALLMENT_BALANCE),
            oldest_due_date=Min("due_date"),
        )
    )
    index = {row["loan_id"]: row for row in rows}
    selected = (
        loans.filter(pk__in=index.keys())
        .select_related("customer", "collector", "business")
    )
    result = []
    for loan in selected:
        row = index[loan.pk]
        result.append({
            "loan": loan,
            "customer": loan.customer,
            "overdue_count": row["overdue_count"],
            "overdue_balance": money(row["overdue_balance"] or ZERO),
            "total_balance": money(loan.outstanding_balance),
            "days_past_due": (today - row["oldest_due_date"]).days,
            "last_action": loan.collection_actions.order_by("-performed_at").first(),
        })
    result.sort(key=lambda row: row["days_past_due"], reverse=True)
    return result


def late_fee_estimate(loan: Loan, today: dt.date | None = None) -> Decimal:
    """Late fee ONLY when the business has it configured and enabled.

    It is neither stored nor charged automatically: it is an informational
    figure that requires a documented policy and a business decision.
    """
    business = loan.business
    if not business.charges_late_fee or to_decimal(business.late_fee_rate) <= ZERO:
        return ZERO
    today = today or today_local()
    cutoff = today - dt.timedelta(days=business.grace_days)
    total = ZERO
    for installment in loan.installments.filter(due_date__lt=cutoff).exclude(
        status=InstallmentStatus.PAID
    ):
        days = (cutoff - installment.due_date).days
        total += to_decimal(installment.balance) * to_decimal(business.late_fee_rate) * days
    return money(total)


def portfolio_breakdown(loans, today: dt.date | None = None) -> dict:
    """Counts and balances per portfolio category."""
    from apps.loans.models import LoanStatus

    today = today or today_local()
    live = loans.live()
    return {
        "due_today": installments_due_on(live, today).count(),
        "upcoming": upcoming_installments(live, 7, today).count(),
        "overdue": overdue_installments(live, today).count(),
        "past_due_loans": live.filter(status=LoanStatus.PAST_DUE).count(),
        "live_loans": live.count(),
        "settled_loans": loans.settled().count(),
        "overdue_balance": overdue_balance_for(live, today),
        "total_balance": money(
            live.aggregate(total=Sum("outstanding_balance"))["total"] or ZERO),
        "customers_with_several_loans": (
            live.values("customer_id")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
            .count()
        ),
        "partially_paid": live.filter(
            Q(principal_paid__gt=0) | Q(interest_paid__gt=0)
        ).count(),
    }
