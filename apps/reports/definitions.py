"""Report catalog.

Every report declares its columns and a function that returns the rows,
taking the user (so permissions are respected) and the filters. That way
the view, the CSV export and the Excel export all share the same data.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from django.db.models import Count, DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.utils.translation import gettext_lazy as _

from apps.core.dates import today_local
from apps.core.money import ZERO, money
from apps.loans.models import DISBURSED_STATUSES, Installment, InstallmentStatus, Loan
from apps.payments.models import Payment
from apps.users import permissions

DECIMAL = DecimalField(max_digits=14, decimal_places=2)
SQL_ZERO = Value(ZERO, output_field=DECIMAL)


@dataclass
class Report:
    key: str
    name: str
    description: str
    columns: list[tuple[str, str]]
    generator: Callable
    filters: list[str] = field(default_factory=lambda: ["start", "end"])


# --------------------------------------------------------------------------
# Scope helpers
# --------------------------------------------------------------------------
def _loans(user, filters):
    queryset = permissions.filter_by_business(Loan.objects.all(), user)
    queryset = permissions.filter_collector_portfolio(queryset, user)
    if filters.get("collector"):
        queryset = queryset.filter(collector=filters["collector"])
    if filters.get("status"):
        queryset = queryset.filter(status=filters["status"])
    return queryset.select_related("customer", "collector")


def _payments(user, filters):
    queryset = permissions.filter_by_business(Payment.objects.all(), user)
    queryset = permissions.filter_collector_portfolio(queryset, user)
    if filters.get("collector"):
        queryset = queryset.filter(collector=filters["collector"])
    if filters.get("method"):
        queryset = queryset.filter(method=filters["method"])
    return queryset.select_related("customer", "loan", "collector")


def _date_range(queryset, filters, field_name):
    if filters.get("start"):
        queryset = queryset.filter(**{f"{field_name}__gte": filters["start"]})
    if filters.get("end"):
        queryset = queryset.filter(**{f"{field_name}__lte": filters["end"]})
    return queryset


# --------------------------------------------------------------------------
# Generators
# --------------------------------------------------------------------------
def loans_granted(user, filters):
    queryset = _date_range(
        _loans(user, filters).filter(status__in=DISBURSED_STATUSES),
        filters, "disbursement_date")
    for loan in queryset.order_by("-disbursement_date"):
        yield {
            "reference": loan.reference,
            "customer": str(loan.customer),
            "disbursement_date": loan.disbursement_date,
            "principal": loan.principal,
            "interest": loan.total_interest,
            "total": loan.total_payable,
            "installments": loan.installment_count,
            "frequency": loan.get_payment_frequency_display(),
            "status": loan.get_status_display(),
            "collector": str(loan.collector or "-"),
        }


def loans_by_status(user, filters):
    from apps.loans.models import LoanStatus

    rows = (
        _loans(user, filters).values("status")
        .annotate(count=Count("id"),
                  principal=Coalesce(Sum("principal"), SQL_ZERO),
                  balance=Coalesce(Sum("outstanding_balance"), SQL_ZERO))
        .order_by("status")
    )
    labels = dict(LoanStatus.choices)
    for row in rows:
        yield {
            "status": str(labels.get(row["status"], row["status"])),
            "count": row["count"],
            "principal": money(row["principal"]),
            "balance": money(row["balance"]),
        }


def payments_in_period(user, filters):
    queryset = _date_range(_payments(user, filters).confirmed(), filters, "paid_at__date")
    for payment in queryset.order_by("-paid_at"):
        yield {
            "reference": payment.reference,
            "date": payment.paid_at.strftime("%d/%m/%Y %H:%M"),
            "customer": str(payment.customer),
            "loan": payment.loan.reference,
            "amount": payment.amount,
            "allocated": payment.allocated_amount,
            "overpayment": payment.overpayment,
            "method": payment.get_method_display(),
            "kind": payment.get_kind_display(),
            "collector": str(payment.collector or "-"),
            "received_by": str(payment.received_by),
        }


def cash_flow(user, filters):
    """Cash received per month (write-offs excluded)."""
    queryset = _date_range(_payments(user, filters).cash_received(),
                           filters, "paid_at__date")
    rows = (
        queryset.annotate(month=TruncMonth("paid_at"))
        .values("month")
        .annotate(total=Coalesce(Sum("amount"), SQL_ZERO), count=Count("id"))
        .order_by("month")
    )
    for row in rows:
        yield {
            "month": row["month"].strftime("%m/%Y") if row["month"] else "-",
            "payment_count": row["count"],
            "total_received": money(row["total"]),
        }


def portfolio_status(user, filters):
    today = today_local()
    queryset = _loans(user, filters).live()
    for loan in queryset.order_by("customer__last_name"):
        overdue = loan.overdue_balance
        yield {
            "reference": loan.reference,
            "customer": str(loan.customer),
            "total_balance": loan.outstanding_balance,
            "overdue_balance": overdue,
            "not_yet_due": money(loan.outstanding_balance - overdue),
            "days_past_due": loan.days_past_due,
            "status": loan.get_status_display(),
            "as_of": today.strftime("%d/%m/%Y"),
        }


def balances_by_customer(user, filters):
    queryset = _loans(user, filters).live()
    rows = (
        queryset.values("customer_id", "customer__first_name", "customer__last_name",
                        "customer__second_last_name", "customer__phone")
        .annotate(loans=Count("id"),
                  balance=Coalesce(Sum("outstanding_balance"), SQL_ZERO),
                  principal=Coalesce(Sum("principal"), SQL_ZERO))
        .order_by("-balance")
    )
    for row in rows:
        name = " ".join(filter(None, [
            row["customer__first_name"], row["customer__last_name"],
            row["customer__second_last_name"]]))
        yield {
            "customer": name,
            "phone": row["customer__phone"],
            "live_loans": row["loans"],
            "principal_lent": money(row["principal"]),
            "outstanding_balance": money(row["balance"]),
        }


def interest_summary(user, filters):
    queryset = _date_range(
        _loans(user, filters).filter(status__in=DISBURSED_STATUSES),
        filters, "disbursement_date")
    totals = queryset.aggregate(
        contractual=Coalesce(Sum("total_interest"), SQL_ZERO),
        collected=Coalesce(Sum("interest_paid"), SQL_ZERO),
        principal=Coalesce(Sum("principal"), SQL_ZERO),
        principal_recovered=Coalesce(Sum("principal_paid"), SQL_ZERO),
    )
    yield {
        "disbursed_principal": money(totals["principal"]),
        "principal_recovered": money(totals["principal_recovered"]),
        "contractual_interest": money(totals["contractual"]),
        "interest_collected": money(totals["collected"]),
        "interest_pending": money(totals["contractual"] - totals["collected"]),
    }


def principal_recovery(user, filters):
    queryset = _date_range(
        _loans(user, filters).filter(status__in=DISBURSED_STATUSES),
        filters, "disbursement_date")
    for loan in queryset.order_by("-disbursement_date"):
        yield {
            "reference": loan.reference,
            "customer": str(loan.customer),
            "principal": loan.principal,
            "principal_recovered": loan.principal_paid,
            "interest_collected": loan.interest_paid,
            "outstanding_balance": loan.outstanding_balance,
            "percent_paid": loan.percent_paid,
        }


def collector_report(user, filters):
    from apps.dashboard.services import collector_performance

    for row in collector_performance(
        user, start=filters.get("start"), end=filters.get("end")
    ):
        yield {
            "collector": str(row["collector"]),
            "payments_received": row["payments_received"],
            "payment_count": row["payment_count"],
            "assigned_portfolio": row["assigned_portfolio"],
            "assigned_loans": row["assigned_loans"],
            "overdue_balance": row["overdue_balance"],
            "actions": row["actions"],
            "promises": row["promises"],
            "promises_kept": row["promises_kept"],
        }


def payment_history(user, filters):
    queryset = _date_range(_payments(user, filters), filters, "paid_at__date")
    for payment in queryset.order_by("customer__last_name", "-paid_at"):
        yield {
            "customer": str(payment.customer),
            "loan": payment.loan.reference,
            "payment_reference": payment.reference,
            "date": payment.paid_at.strftime("%d/%m/%Y"),
            "amount": payment.amount,
            "status": payment.get_status_display(),
            "method": payment.get_method_display(),
        }


def repeated_delinquency(user, filters):
    """Loans with the most installments still overdue."""
    queryset = _loans(user, filters)
    today = today_local()
    rows = (
        Installment.objects.filter(loan__in=queryset)
        .filter(due_date__lt=today)
        .exclude(status=InstallmentStatus.PAID)
        .values("loan_id")
        .annotate(overdue=Count("id"),
                  balance=Coalesce(Sum(F("scheduled_amount") - F("amount_paid"),
                                       output_field=DECIMAL), SQL_ZERO))
        .filter(overdue__gte=filters.get("min_overdue") or 1)
        .order_by("-overdue")
    )
    index = {row["loan_id"]: row for row in rows}
    for loan in queryset.filter(pk__in=index.keys()):
        row = index[loan.pk]
        yield {
            "reference": loan.reference,
            "customer": str(loan.customer),
            "phone": loan.customer.phone,
            "overdue_installments": row["overdue"],
            "overdue_balance": money(row["balance"]),
            "days_past_due": loan.days_past_due,
            "collector": str(loan.collector or "-"),
        }


def largest_borrowers(user, filters):
    queryset = _date_range(
        _loans(user, filters).filter(status__in=DISBURSED_STATUSES),
        filters, "disbursement_date")
    rows = (
        queryset.values("customer__first_name", "customer__last_name",
                        "customer__second_last_name")
        .annotate(count=Count("id"), principal=Coalesce(Sum("principal"), SQL_ZERO),
                  paid=Coalesce(Sum("principal_paid"), SQL_ZERO))
        .order_by("-principal")[:100]
    )
    for row in rows:
        name = " ".join(filter(None, [
            row["customer__first_name"], row["customer__last_name"],
            row["customer__second_last_name"]]))
        yield {
            "customer": name,
            "loans": row["count"],
            "historical_principal": money(row["principal"]),
            "principal_recovered": money(row["paid"]),
        }


REPORTS: dict[str, Report] = {
    report.key: report for report in [
        Report("loans_granted", _("Loans granted in the period"),
               _("Loans disbursed within the date range."),
               [("reference", _("Reference")), ("customer", _("Customer")),
                ("disbursement_date", _("Disbursed")),
                ("principal", _("Principal")), ("interest", _("Interest")),
                ("total", _("Total")), ("installments", _("Installments")),
                ("frequency", _("Frequency")), ("status", _("Status")),
                ("collector", _("Collector"))],
               loans_granted),
        Report("loans_by_status", _("Live and settled loans"),
               _("Count and balances per loan status."),
               [("status", _("Status")), ("count", _("Loans")),
                ("principal", _("Principal")), ("balance", _("Outstanding balance"))],
               loans_by_status),
        Report("payments", _("Payments in the period"),
               _("Detail of confirmed payments (daily, weekly or monthly by range)."),
               [("reference", _("Reference")), ("date", _("Date")),
                ("customer", _("Customer")), ("loan", _("Loan")),
                ("amount", _("Amount")), ("allocated", _("Allocated")),
                ("overpayment", _("Overpayment")), ("method", _("Method")),
                ("kind", _("Kind")), ("collector", _("Collector")),
                ("received_by", _("Registered by"))],
               payments_in_period),
        Report("cash_flow", _("Cash inflow"),
               _("Money received per month. Write-offs are not included."),
               [("month", _("Month")), ("payment_count", _("Payments")),
                ("total_received", _("Total received"))],
               cash_flow),
        Report("portfolio", _("Live and past-due portfolio"),
               _("Total, overdue and not-yet-due balance of every live loan."),
               [("reference", _("Reference")), ("customer", _("Customer")),
                ("total_balance", _("Total balance")),
                ("overdue_balance", _("Overdue balance")),
                ("not_yet_due", _("Not yet due")),
                ("days_past_due", _("Days past due")), ("status", _("Status")),
                ("as_of", _("As of"))],
               portfolio_status),
        Report("customer_balances", _("Outstanding balance per customer"),
               _("How much each customer owes in total."),
               [("customer", _("Customer")), ("phone", _("Phone")),
                ("live_loans", _("Live loans")),
                ("principal_lent", _("Principal lent")),
                ("outstanding_balance", _("Outstanding balance"))],
               balances_by_customer),
        Report("interest", _("Contractual and collected interest"),
               _("Comparison between what was agreed and what was actually collected."),
               [("disbursed_principal", _("Disbursed principal")),
                ("principal_recovered", _("Principal recovered")),
                ("contractual_interest", _("Contractual interest")),
                ("interest_collected", _("Interest collected")),
                ("interest_pending", _("Interest pending"))],
               interest_summary),
        Report("recovery", _("Principal recovery"),
               _("Recovery progress loan by loan."),
               [("reference", _("Reference")), ("customer", _("Customer")),
                ("principal", _("Principal")),
                ("principal_recovered", _("Principal recovered")),
                ("interest_collected", _("Interest collected")),
                ("outstanding_balance", _("Outstanding balance")),
                ("percent_paid", _("% paid"))],
               principal_recovery),
        Report("collectors", _("Collector performance"),
               _("Payments received, assigned portfolio and actions. The amount "
                 "received is NOT business profit."),
               [("collector", _("Collector")),
                ("payments_received", _("Payments received")),
                ("payment_count", _("No. of payments")),
                ("assigned_portfolio", _("Assigned portfolio")),
                ("assigned_loans", _("Loans")),
                ("overdue_balance", _("Overdue balance")), ("actions", _("Actions")),
                ("promises", _("Promises")), ("promises_kept", _("Kept"))],
               collector_report),
        Report("payment_history", _("Payment history"),
               _("Every payment, reversed ones included, ordered by customer."),
               [("customer", _("Customer")), ("loan", _("Loan")),
                ("payment_reference", _("Payment reference")), ("date", _("Date")),
                ("amount", _("Amount")), ("status", _("Status")),
                ("method", _("Method"))],
               payment_history),
        Report("delinquency", _("Loans with repeated delinquency"),
               _("Loans with unpaid overdue installments."),
               [("reference", _("Reference")), ("customer", _("Customer")),
                ("phone", _("Phone")),
                ("overdue_installments", _("Overdue installments")),
                ("overdue_balance", _("Overdue balance")),
                ("days_past_due", _("Days past due")), ("collector", _("Collector"))],
               repeated_delinquency),
        Report("largest_borrowers", _("Customers with the largest lending volume"),
               _("Ranking by historical disbursed principal."),
               [("customer", _("Customer")), ("loans", _("Loans")),
                ("historical_principal", _("Historical principal")),
                ("principal_recovered", _("Principal recovered"))],
               largest_borrowers),
    ]
}
