"""Credit history and repayment behaviour of a customer."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, F, ProtectedError, Q, Sum
from django.utils.translation import gettext as _

from apps.core.dates import today_local
from apps.core.money import ZERO, money


def customer_summary(customer) -> dict:
    """Internal credit history of the customer.

    This is information for a person to decide with: the system never
    approves or rejects automatically based on a score.
    """
    from apps.loans.models import DISBURSED_STATUSES, InstallmentStatus, LoanStatus
    from apps.payments.models import Payment, PaymentStatus

    loans = customer.loans.all()
    totals = loans.aggregate(
        total=Count("id"),
        live=Count("id", filter=Q(status__in=[LoanStatus.DISBURSED,
                                              LoanStatus.ACTIVE,
                                              LoanStatus.PAST_DUE])),
        settled=Count("id", filter=Q(status=LoanStatus.SETTLED)),
        restructured=Count("id", filter=Q(status=LoanStatus.RESTRUCTURED)),
        historical_principal=Sum("principal", filter=Q(status__in=DISBURSED_STATUSES)),
        balance=Sum("outstanding_balance"),
    )

    paid = Payment.objects.filter(
        customer=customer, status=PaymentStatus.CONFIRMED
    ).aggregate(total=Sum("amount"))["total"] or ZERO

    installments = _customer_installments(customer)
    today = today_local()
    overdue = installments.filter(due_date__lt=today).exclude(
        status=InstallmentStatus.PAID)
    paid_installments = installments.filter(status=InstallmentStatus.PAID)
    paid_on_time = paid_installments.filter(settled_on__lte=F("due_date")).count()
    total_paid_installments = paid_installments.count()

    overdue_balance = ZERO
    max_days_past_due = 0
    for installment in overdue.select_related("loan"):
        overdue_balance += installment.balance
        max_days_past_due = max(max_days_past_due, installment.days_past_due)

    punctuality = (
        Decimal(paid_on_time * 100) / Decimal(total_paid_installments)
        if total_paid_installments
        else ZERO
    )

    return {
        "customer": customer,
        "loan_count": totals["total"] or 0,
        "live_loan_count": totals["live"] or 0,
        "settled_loans": totals["settled"] or 0,
        "restructured_loans": totals["restructured"] or 0,
        "total_borrowed": money(totals["historical_principal"] or ZERO),
        "total_paid": money(paid),
        "outstanding_balance": money(totals["balance"] or ZERO),
        "overdue_balance": money(overdue_balance),
        "overdue_installments": overdue.count(),
        "paid_installments": total_paid_installments,
        "installments_paid_on_time": paid_on_time,
        "max_days_past_due": max_days_past_due,
        "punctuality": money(punctuality),
    }


def _customer_installments(customer):
    from apps.loans.models import Installment

    return Installment.objects.filter(loan__customer=customer)


def payment_history(customer, limit: int | None = None):
    from apps.payments.models import Payment

    queryset = (
        Payment.objects.filter(customer=customer)
        .select_related("loan")
        .order_by("-paid_at")
    )
    return queryset[:limit] if limit else queryset


class CustomerDeletionError(Exception):
    """The customer cannot be deleted (it has financial history)."""


def can_delete_customer(customer) -> bool:
    """Only customers without loans can be deleted.

    Their loans are deleted first (each loan takes its payments with it).
    """
    return not customer.loans.exists()


@transaction.atomic
def delete_customer(customer, user) -> None:
    """Delete a customer with no financial history and record it in the audit log."""
    from apps.audit.models import AuditAction
    from apps.audit.services import log
    from apps.customers.models import Customer

    customer = Customer.objects.select_for_update().get(pk=customer.pk)
    if not can_delete_customer(customer):
        raise CustomerDeletionError(
            _("%(name)s has registered loans. Delete them first to be able to delete "
              "the customer.") % {"name": customer.full_name})
    # Snapshot first: after delete() the row (and its pk) no longer exist.
    snapshot = {
        "full_name": customer.full_name,
        "phone": customer.phone,
    }
    log(AuditAction.DELETE,
        _("Customer %(name)s deleted") % {"name": customer.full_name},
        target=customer, user=user, data=snapshot)
    try:
        customer.delete()
    except ProtectedError as error:  # a related record appeared in the meantime
        raise CustomerDeletionError(
            _("%(name)s has related records and cannot be deleted.") % {
                "name": customer.full_name}) from error
