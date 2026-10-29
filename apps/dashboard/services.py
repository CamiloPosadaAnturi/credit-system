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

from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce, TruncDate

from apps.collections.services import (
    installments_due_on,
    installments_of,
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
    """Dashboard figures in three aggregate queries (loans, payments and
    installments) instead of one query per figure: with a remote database
    every query is a network round trip."""
    from apps.loans.models import LIVE_STATUSES, InstallmentStatus

    loans, payments = scope(user, business)
    today = today_local()
    start = start or today.replace(day=1)
    end = end or today

    in_period = Q(status__in=DISBURSED_STATUSES,
                  disbursement_date__gte=start, disbursement_date__lte=end)
    is_live = Q(status__in=LIVE_STATUSES)
    loan_totals = loans.aggregate(
        principal=Coalesce(Sum("principal", filter=in_period), _zero()),
        interest=Coalesce(Sum("total_interest", filter=in_period), _zero()),
        payable=Coalesce(Sum("total_payable", filter=in_period), _zero()),
        granted=Count("id", filter=in_period),
        outstanding=Coalesce(Sum("outstanding_balance", filter=is_live), _zero()),
        live=Count("id", filter=is_live),
        settled=Count("id", filter=Q(status=LoanStatus.SETTLED)),
        past_due=Count("id", filter=Q(status=LoanStatus.PAST_DUE)),
        customers=Count("customer", filter=is_live, distinct=True),
    )

    in_range = Q(paid_at__date__gte=start, paid_at__date__lte=end)
    is_today = Q(paid_at__date=today)
    payment_totals = payments.cash_received().aggregate(
        collected=Coalesce(Sum("amount", filter=in_range), _zero()),
        today=Coalesce(Sum("amount", filter=is_today), _zero()),
        today_count=Count("id", filter=is_today),
    )

    balance = ExpressionWrapper(F("scheduled_amount") - F("amount_paid"), output_field=DECIMAL)
    overdue_q = Q(due_date__lt=today)
    today_q = Q(due_date=today)
    upcoming_q = Q(due_date__gt=today, due_date__lte=today + dt.timedelta(days=7))
    installment_totals = (
        installments_of(loans.live()).exclude(status=InstallmentStatus.PAID).aggregate(
            overdue=Coalesce(Sum(balance, filter=overdue_q), _zero()),
            overdue_count=Count("id", filter=overdue_q),
            scheduled_today=Coalesce(Sum(balance, filter=today_q), _zero()),
            scheduled_today_count=Count("id", filter=today_q),
            upcoming_count=Count("id", filter=upcoming_q),
        )
    )
    collected = payment_totals["collected"]
    outstanding = loan_totals["outstanding"]
    overdue = installment_totals["overdue"]

    return {
        "start": start,
        "end": end,
        "disbursed_principal": money(loan_totals["principal"]),
        "contractual_interest": money(loan_totals["interest"]),
        "contractual_total": money(loan_totals["payable"]),
        "loans_granted": loan_totals["granted"],
        "total_collected": money(collected),
        "outstanding_balance": money(outstanding),
        "overdue_balance": money(overdue),
        "live_loans": loan_totals["live"],
        "settled_loans": loan_totals["settled"],
        "past_due_loans": loan_totals["past_due"],
        "active_customers": loan_totals["customers"],
        "scheduled_today_count": installment_totals["scheduled_today_count"],
        "scheduled_today": money(installment_totals["scheduled_today"]),
        "collected_today": money(payment_totals["today"]),
        "collected_today_count": payment_totals["today_count"],
        "overdue_installments": installment_totals["overdue_count"],
        "upcoming_installments": installment_totals["upcoming_count"],
        "recovery_rate": ratio(collected, loan_totals["payable"]),
        "overdue_portfolio_rate": ratio(money(overdue), outstanding),
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

    Every figure comes from one grouped query for all the collectors, so the
    number of queries does not grow with the collectors or their promises.
    """
    from apps.collections.models import CollectionAction
    from apps.collections.services import INSTALLMENT_BALANCE, installments_of
    from apps.loans.models import InstallmentStatus
    from apps.payments.models import PaymentStatus
    from apps.users.models import Role, User

    collectors = list(User.objects.filter(role=Role.COLLECTOR))
    if not collectors:
        return []
    ids = [collector.pk for collector in collectors]
    loans, payments = scope(user, business)

    received = payments.cash_received().filter(collector__in=ids)
    actions = CollectionAction.objects.filter(user__in=ids)
    if start:
        received = received.filter(paid_at__date__gte=start)
        actions = actions.filter(performed_at__date__gte=start)
    if end:
        received = received.filter(paid_at__date__lte=end)
        actions = actions.filter(performed_at__date__lte=end)

    def by(queryset, key, **aggregates):
        rows = queryset.order_by().values(key).annotate(**aggregates)
        return {row[key]: row for row in rows}

    received = by(received, "collector",
                  total=Coalesce(Sum("amount"), _zero()), count=Count("id"))
    portfolio_loans = loans.live().filter(collector__in=ids)
    portfolio = by(portfolio_loans, "collector",
                   balance=Coalesce(Sum("outstanding_balance"), _zero()), count=Count("id"))
    overdue = by(
        installments_of(portfolio_loans).filter(due_date__lt=today_local())
        .exclude(status=InstallmentStatus.PAID),
        "loan__collector", total=Sum(INSTALLMENT_BALANCE))
    action_counts = by(actions, "user", total=Count("id"),
                       promises=Count("id", filter=Q(promised_amount__gt=0)))
    # A promise is kept when the confirmed payments of the loan made after the
    # action add up to the promised amount (same rule as promise_kept).
    paid_after = (
        Payment.objects.filter(loan=OuterRef("loan"), status=PaymentStatus.CONFIRMED,
                               paid_at__gte=OuterRef("performed_at"))
        .order_by().values("loan").annotate(total=Sum("amount")).values("total")
    )
    kept = by(
        actions.filter(promised_amount__gt=0, promise_date__isnull=False)
        .alias(paid_after=Coalesce(Subquery(paid_after), _zero()))
        .filter(paid_after__gte=F("promised_amount")),
        "user", total=Count("id"))

    rows = []
    for collector in collectors:
        pk = collector.pk
        rows.append({
            "collector": collector,
            "payments_received": money(received.get(pk, {}).get("total", ZERO)),
            "payment_count": received.get(pk, {}).get("count", 0),
            "assigned_portfolio": money(portfolio.get(pk, {}).get("balance", ZERO)),
            "assigned_loans": portfolio.get(pk, {}).get("count", 0),
            "actions": action_counts.get(pk, {}).get("total", 0),
            "promises": action_counts.get(pk, {}).get("promises", 0),
            "promises_kept": kept.get(pk, {}).get("total", 0),
            "overdue_balance": money(overdue.get(pk, {}).get("total") or ZERO),
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
