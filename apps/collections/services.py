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

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Min, Prefetch, Q, Sum

from apps.core.dates import today_local
from apps.core.money import ZERO, money
from apps.loans.models import LIVE_STATUSES, Installment, InstallmentStatus

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
    from apps.collections.models import CollectionAction

    latest_first = CollectionAction.objects.order_by("-performed_at")
    selected = (
        loans.filter(pk__in=index.keys())
        .select_related("customer", "collector", "business")
        .prefetch_related(Prefetch("collection_actions", queryset=latest_first,
                                   to_attr="actions_latest_first"))
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
            "last_action": next(iter(loan.actions_latest_first), None),
        })
    result.sort(key=lambda row: row["days_past_due"], reverse=True)
    return result


def portfolio_breakdown(loans, today: dt.date | None = None) -> dict:
    """Counts and balances per portfolio category, in three queries."""
    from apps.loans.models import LoanStatus

    today = today or today_local()
    live = loans.live()
    loan_totals = loans.aggregate(
        live=Count("id", filter=Q(status__in=LIVE_STATUSES)),
        past_due=Count("id", filter=Q(status=LoanStatus.PAST_DUE)),
        settled=Count("id", filter=Q(status=LoanStatus.SETTLED)),
        total_balance=Sum("outstanding_balance", filter=Q(status__in=LIVE_STATUSES)),
        partially_paid=Count("id", filter=Q(status__in=LIVE_STATUSES)
                             & (Q(principal_paid__gt=0) | Q(interest_paid__gt=0))),
    )
    upcoming = Q(due_date__gt=today, due_date__lte=today + dt.timedelta(days=7))
    installment_totals = (
        installments_of(live).exclude(status=InstallmentStatus.PAID).aggregate(
            due_today=Count("id", filter=Q(due_date=today)),
            upcoming=Count("id", filter=upcoming),
            overdue=Count("id", filter=Q(due_date__lt=today)),
            overdue_balance=Sum(INSTALLMENT_BALANCE, filter=Q(due_date__lt=today)),
        )
    )
    return {
        "due_today": installment_totals["due_today"],
        "upcoming": installment_totals["upcoming"],
        "overdue": installment_totals["overdue"],
        "past_due_loans": loan_totals["past_due"],
        "live_loans": loan_totals["live"],
        "settled_loans": loan_totals["settled"],
        "overdue_balance": money(installment_totals["overdue_balance"] or ZERO),
        "total_balance": money(loan_totals["total_balance"] or ZERO),
        "customers_with_several_loans": (
            live.order_by().values("customer_id")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
            .count()
        ),
        "partially_paid": loan_totals["partially_paid"],
    }
