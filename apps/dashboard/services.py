"""Dashboard indicators.

Definitions (mixing these concepts up is the most common mistake in this
kind of business):

* Disbursed principal: money lent out in the period. It leaves the
  business; it is not income.
* Contractual interest: interest agreed on those loans. It accrues per the
  contract; it is not collected profit.
* Total collected: money actually received in the period (confirmed
  payments, write-offs excluded).
* Outstanding balance: what is left to collect on the live loans.
* Overdue balance: the part of the outstanding balance already past due.
* Recovery rate: collected / contractual total of the loans disbursed in
  the period.
* Overdue portfolio rate: overdue balance / outstanding balance.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce, TruncDate

from apps.collections.services import (
    installments_due_on,
    overdue_balance_for,
    overdue_installments,
    upcoming_installments,
)
from apps.core.dates import today_local
from apps.core.money import ZERO, money
from apps.loans.models import DISBURSED_STATUSES, Loan, LoanStatus
from apps.payments.models import Payment
from apps.users import permissions

DECIMAL = DecimalField(max_digits=14, decimal_places=2)


def _zero():
    return Value(Decimal("0"), output_field=DECIMAL)


def ratio(part, whole) -> Decimal:
    part = part or ZERO
    whole = whole or ZERO
    if whole <= ZERO:
        return ZERO
    return money(Decimal(part) * 100 / Decimal(whole))


def scope(user, business=None):
    """Loans and payments the user may see, optionally for one business."""
    loans = permissions.filter_by_business(Loan.objects.all(), user)
    loans = permissions.filter_collector_portfolio(loans, user)
    payments = permissions.filter_by_business(Payment.objects.all(), user)
    payments = permissions.filter_collector_portfolio(payments, user)
    if business:
        loans = loans.filter(business=business)
        payments = payments.filter(business=business)
    return loans, payments


def indicators(user, business=None, start: dt.date | None = None,
               end: dt.date | None = None) -> dict:
    loans, payments = scope(user, business)
    today = today_local()
    start = start or today.replace(day=1)
    end = end or today

    disbursed = loans.filter(status__in=DISBURSED_STATUSES)
    in_period = disbursed.filter(disbursement_date__gte=start, disbursement_date__lte=end)

    lending = in_period.aggregate(
        principal=Coalesce(Sum("principal"), _zero()),
        interest=Coalesce(Sum("total_interest"), _zero()),
        payable=Coalesce(Sum("total_payable"), _zero()),
        count=Count("id"),
    )

    period_payments = payments.cash_received().filter(
        paid_at__date__gte=start, paid_at__date__lte=end)
    collected = period_payments.aggregate(
        total=Coalesce(Sum("amount"), _zero()))["total"]

    live = loans.live()
    outstanding = live.aggregate(
        total=Coalesce(Sum("outstanding_balance"), _zero()))["total"]
    overdue = overdue_balance_for(live, today)

    today_payments = payments.cash_received().filter(paid_at__date=today).aggregate(
        total=Coalesce(Sum("amount"), _zero()), count=Count("id"))
    today_installments = installments_due_on(live, today)
    scheduled_today = today_installments.aggregate(
        total=Coalesce(Sum(F("scheduled_amount") - F("amount_paid"),
                           output_field=DECIMAL), _zero()))["total"]

    active_customers = live.values("customer_id").distinct().count()

    return {
        "start": start,
        "end": end,
        "disbursed_principal": money(lending["principal"]),
        "contractual_interest": money(lending["interest"]),
        "contractual_total": money(lending["payable"]),
        "loans_granted": lending["count"],
        "total_collected": money(collected),
        "outstanding_balance": money(outstanding),
        "overdue_balance": money(overdue),
        "live_loans": live.count(),
        "settled_loans": loans.filter(status=LoanStatus.SETTLED).count(),
        "past_due_loans": loans.filter(status=LoanStatus.PAST_DUE).count(),
        "active_customers": active_customers,
        "scheduled_today_count": today_installments.count(),
        "scheduled_today": money(scheduled_today),
        "collected_today": money(today_payments["total"]),
        "collected_today_count": today_payments["count"],
        "overdue_installments": overdue_installments(live, today).count(),
        "upcoming_installments": upcoming_installments(live, 7, today).count(),
        "recovery_rate": ratio(collected, lending["payable"]),
        "overdue_portfolio_rate": ratio(overdue, outstanding),
    }


# --------------------------------------------------------------------------
# Dashboard sections
# --------------------------------------------------------------------------
def customers_due_today(user, business=None, date: dt.date | None = None):
    loans, _ = scope(user, business)
    return installments_due_on(loans.live(), date or today_local())


def customers_past_due(user, business=None):
    from apps.collections.services import past_due_summary

    loans, _ = scope(user, business)
    return past_due_summary(loans.live())


def top_borrowers(user, business=None, start=None, end=None, limit=10):
    """Customers who borrowed the most (by amount and by count)."""
    loans, _ = scope(user, business)
    queryset = loans.filter(status__in=DISBURSED_STATUSES)
    if start:
        queryset = queryset.filter(disbursement_date__gte=start)
    if end:
        queryset = queryset.filter(disbursement_date__lte=end)
    base = (
        queryset.values("customer_id", "customer__first_name", "customer__last_name",
                        "customer__second_last_name")
        .annotate(principal=Coalesce(Sum("principal"), _zero()), count=Count("id"))
    )
    return {
        "by_amount": list(base.order_by("-principal")[:limit]),
        "by_count": list(base.order_by("-count", "-principal")[:limit]),
    }


def top_payers(user, business=None, start=None, end=None, limit=10):
    """Customers who paid the most: in the period and across their history."""
    _, payments = scope(user, business)
    confirmed = payments.cash_received()
    period = confirmed
    if start:
        period = period.filter(paid_at__date__gte=start)
    if end:
        period = period.filter(paid_at__date__lte=end)

    def group(queryset):
        return list(
            queryset.values("customer_id", "customer__first_name",
                            "customer__last_name", "customer__second_last_name")
            .annotate(total=Coalesce(Sum("amount"), _zero()), count=Count("id"))
            .order_by("-total")[:limit]
        )

    return {"period": group(period), "historical": group(confirmed)}


def collector_performance(user, business=None, start=None, end=None):
    """Per-collector indicators.

    WARNING: the amount a collector received is NOT business profit; it is
    collected money that includes both principal and interest.
    """
    from apps.collections.models import CollectionAction
    from apps.users.models import Role, User

    loans, payments = scope(user, business)
    collectors = User.objects.filter(role=Role.COLLECTOR)

    rows = []
    for collector in collectors:
        collector_payments = payments.cash_received().filter(collector=collector)
        if start:
            collector_payments = collector_payments.filter(paid_at__date__gte=start)
        if end:
            collector_payments = collector_payments.filter(paid_at__date__lte=end)
        totals = collector_payments.aggregate(
            total=Coalesce(Sum("amount"), _zero()), count=Count("id"))

        portfolio = loans.live().filter(collector=collector)
        portfolio_totals = portfolio.aggregate(
            balance=Coalesce(Sum("outstanding_balance"), _zero()), count=Count("id"))

        actions = CollectionAction.objects.filter(user=collector)
        if start:
            actions = actions.filter(performed_at__date__gte=start)
        if end:
            actions = actions.filter(performed_at__date__lte=end)
        promises = actions.filter(promised_amount__gt=0)
        kept = sum(1 for action in promises if action.promise_kept)

        rows.append({
            "collector": collector,
            "payments_received": money(totals["total"]),
            "payment_count": totals["count"],
            "assigned_portfolio": money(portfolio_totals["balance"]),
            "assigned_loans": portfolio_totals["count"],
            "actions": actions.count(),
            "promises": promises.count(),
            "promises_kept": kept,
            "overdue_balance": overdue_balance_for(portfolio),
        })
    rows.sort(key=lambda row: row["payments_received"], reverse=True)
    return rows


def recent_activity(user, business=None, limit=10) -> dict:
    from apps.customers.models import Customer

    loans, payments = scope(user, business)
    customers = permissions.filter_by_business(Customer.objects.all(), user)
    if business:
        customers = customers.filter(business=business)
    return {
        "new_customers": customers.order_by("-created_at")[:limit],
        "new_loans": loans.select_related("customer").order_by("-created_at")[:limit],
        "disbursements": loans.filter(disbursement_date__isnull=False)
        .select_related("customer").order_by("-disbursement_date", "-id")[:limit],
        "recent_payments": payments.confirmed().select_related("customer", "loan")
        .order_by("-paid_at")[:limit],
    }


def collection_series(user, business=None, days: int = 30) -> dict:
    """Daily collection series for the dashboard chart."""
    _, payments = scope(user, business)
    today = today_local()
    start = today - dt.timedelta(days=days - 1)
    rows = (
        payments.cash_received()
        .filter(paid_at__date__gte=start)
        .annotate(day=TruncDate("paid_at"))
        .values("day")
        .annotate(total=Coalesce(Sum("amount"), _zero()))
        .order_by("day")
    )
    index = {row["day"]: row["total"] for row in rows}
    labels, values = [], []
    for offset in range(days):
        day = start + dt.timedelta(days=offset)
        labels.append(day.strftime("%d/%m"))
        values.append(float(index.get(day, 0)))
    return {"labels": labels, "values": values}


def portfolio_composition(user, business=None) -> dict:
    """Distribution of the portfolio by loan status (doughnut chart)."""
    loans, _ = scope(user, business)
    rows = (
        loans.values("status")
        .annotate(count=Count("id"),
                  balance=Coalesce(Sum("outstanding_balance"), _zero()))
        .order_by("-count")
    )
    labels = [str(dict(LoanStatus.choices).get(row["status"], row["status"]))
              for row in rows]
    return {
        "labels": labels,
        "counts": [row["count"] for row in rows],
        "balances": [float(row["balance"]) for row in rows],
    }


def scheduled_vs_collected(user, business=None, days: int = 14) -> dict:
    """Compare what was scheduled against what was collected, per day."""
    from apps.loans.models import Installment

    loans, payments = scope(user, business)
    today = today_local()
    start = today - dt.timedelta(days=days - 1)

    scheduled = (
        Installment.objects.filter(loan__in=loans, due_date__gte=start, due_date__lte=today)
        .values("due_date")
        .annotate(total=Coalesce(Sum("scheduled_amount"), _zero()))
    )
    scheduled_index = {row["due_date"]: float(row["total"]) for row in scheduled}

    collected = (
        payments.cash_received().filter(paid_at__date__gte=start)
        .annotate(day=TruncDate("paid_at")).values("day")
        .annotate(total=Coalesce(Sum("amount"), _zero()))
    )
    collected_index = {row["day"]: float(row["total"]) for row in collected}

    labels, scheduled_series, collected_series = [], [], []
    for offset in range(days):
        day = start + dt.timedelta(days=offset)
        labels.append(day.strftime("%d/%m"))
        scheduled_series.append(scheduled_index.get(day, 0.0))
        collected_series.append(collected_index.get(day, 0.0))
    return {"labels": labels, "scheduled": scheduled_series,
            "collected": collected_series}
