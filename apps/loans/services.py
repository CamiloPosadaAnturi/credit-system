"""Service layer for the loan life cycle.

Every operation that moves money or changes status goes through here:
views never compute interest or balances on their own.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils.translation import gettext as _

from apps.audit.models import AuditAction
from apps.audit.services import log
from apps.core.dates import today_local
from apps.core.errors import LoanError
from apps.core.money import ZERO, money, to_decimal
from apps.loans.calculations import (
    build_schedule,
    calculate_interest,
    calculate_total_payable,
)
from apps.loans.models import (
    LIVE_STATUSES,
    Installment,
    InstallmentStatus,
    Loan,
    LoanStatus,
)


# --------------------------------------------------------------------------
# References
# --------------------------------------------------------------------------
def generate_reference(business) -> str:
    """Unique reference per business and year: ``LN-<business>-<year>-<sequence>``.

    It is generated inside the caller's transaction; final uniqueness is
    guaranteed by the UNIQUE constraint in the database.
    """
    year = today_local().year
    prefix = f"LN-{business.pk:03d}-{year}-"
    last = (
        Loan.objects.filter(reference__startswith=prefix)
        .order_by("-reference")
        .values_list("reference", flat=True)
        .first()
    )
    sequence = int(last.split("-")[-1]) + 1 if last else 1
    return f"{prefix}{sequence:05d}"


# --------------------------------------------------------------------------
# Creation and terms
# --------------------------------------------------------------------------
@transaction.atomic
def create_loan(
    *,
    customer,
    business,
    principal,
    installment_count: int,
    frequency: str,
    first_payment_date: dt.date,
    user=None,
    collector=None,
    interest_mode: str | None = None,
    interest_rate=None,
    rate_period: str | None = None,
    custom_days: int | None = None,
    application_date: dt.date | None = None,
    notes: str = "",
) -> Loan:
    """Create a loan, already handed out, together with its payment schedule.

    There is no approval stage: the loan is live from its application date.
    The interest rule is copied from the business unless another is given.
    """
    if customer.business_id != business.pk:
        raise LoanError(_("The customer does not belong to the selected business."))
    if customer.is_restricted:
        raise LoanError(
            _("The customer is restricted. Review their history before lending.")
        )
    principal = to_decimal(principal)
    if principal <= ZERO:
        raise LoanError(_("The principal must be greater than zero."))

    rule = business.current_interest_rule()
    mode = interest_mode or rule["interest_mode"]
    rate = to_decimal(interest_rate if interest_rate is not None else rule["interest_rate"])
    period = rate_period or rule["rate_period"]

    interest = calculate_interest(principal, mode, rate, installment_count)
    total = calculate_total_payable(principal, interest)

    loan = Loan(
        reference=generate_reference(business),
        customer=customer,
        business=business,
        collector=collector,
        application_date=application_date or today_local(),
        principal=money(principal),
        interest_mode=mode,
        interest_rate=rate,
        rate_period=period,
        total_interest=interest,
        total_payable=total,
        payment_frequency=frequency,
        custom_days=custom_days,
        installment_count=installment_count,
        first_payment_date=first_payment_date,
        outstanding_balance=total,
        status=LoanStatus.DISBURSED,
        disbursement_date=application_date or today_local(),
        disbursed_by=user,
        notes=notes,
        created_by=user,
        updated_by=user,
    )
    loan.save()
    generate_schedule(loan)
    refresh_status(loan)
    log(
        AuditAction.CREATE,
        _("Loan %(reference)s created for %(customer)s for %(amount)s MXN") % {
            "reference": loan.reference, "customer": customer, "amount": money(principal),
        },
        target=loan, user=user, business=business,
        data={"principal": str(loan.principal), "interest": str(interest),
              "total": str(total), "installments": installment_count},
    )
    return loan


@transaction.atomic
def generate_schedule(loan: Loan) -> list[Installment]:
    """(Re)build the installment schedule of a loan with no payments applied."""
    if loan.installments.filter(amount_paid__gt=0).exists():
        raise LoanError(
            _("The schedule cannot be rebuilt: the loan already has payments applied.")
        )
    loan.installments.all().delete()
    rows = build_schedule(
        loan.principal, loan.total_interest, loan.installment_count,
        loan.first_payment_date, loan.payment_frequency, loan.custom_days,
    )
    installments = Installment.objects.bulk_create(
        [Installment(loan=loan, **row) for row in rows])
    loan.installment_amount = rows[0]["scheduled_amount"]
    loan.final_due_date = rows[-1]["due_date"]
    loan.save(update_fields=["installment_amount", "final_due_date", "updated_at"])
    return installments


# --------------------------------------------------------------------------
# Status transitions
# --------------------------------------------------------------------------
@transaction.atomic
def cancel_loan(loan: Loan, user, reason: str) -> Loan:
    loan = Loan.objects.select_for_update().get(pk=loan.pk)
    if loan.status == LoanStatus.SETTLED:
        raise LoanError(_("A settled loan cannot be cancelled."))
    if loan.total_paid > ZERO:
        raise LoanError(
            _("The loan has payments applied. Reverse the payments before cancelling "
              "or register a restructuring.")
        )
    if not reason:
        raise LoanError(_("You must state the reason for the cancellation."))
    loan.status = LoanStatus.CANCELLED
    loan.cancellation_reason = reason
    loan.outstanding_balance = ZERO
    loan.updated_by = user
    loan.save()
    loan.installments.update(status=InstallmentStatus.PENDING)
    log(
        AuditAction.CANCEL,
        _("Loan %(reference)s cancelled: %(reason)s") % {
            "reference": loan.reference, "reason": reason,
        },
        target=loan, user=user,
    )
    return loan


@transaction.atomic
def restructure_loan(
    loan: Loan,
    user,
    *,
    installment_count: int,
    frequency: str,
    first_payment_date: dt.date,
    interest_mode: str | None = None,
    interest_rate=None,
    notes: str = "",
) -> Loan:
    """Close the current loan and create a new one for the outstanding balance.

    The original loan keeps its history intact: it stays in the
    ``restructured`` status and the new loan points back to it.
    """
    loan = Loan.objects.select_for_update().get(pk=loan.pk)
    if loan.status not in LIVE_STATUSES:
        raise LoanError(_("Only a live loan can be restructured."))
    balance = money(loan.outstanding_balance)
    if balance <= ZERO:
        raise LoanError(_("The loan has no outstanding balance to restructure."))

    new_loan = create_loan(
        customer=loan.customer,
        business=loan.business,
        principal=balance,
        installment_count=installment_count,
        frequency=frequency,
        first_payment_date=first_payment_date,
        user=user,
        collector=loan.collector,
        interest_mode=interest_mode or loan.interest_mode,
        interest_rate=interest_rate if interest_rate is not None else loan.interest_rate,
        rate_period=loan.rate_period,
        notes=notes or _("Restructuring of %(reference)s") % {"reference": loan.reference},
    )
    new_loan.original_loan = loan
    new_loan.save(update_fields=["original_loan"])

    loan.status = LoanStatus.RESTRUCTURED
    loan.outstanding_balance = ZERO
    loan.updated_by = user
    loan.save(update_fields=["status", "outstanding_balance", "updated_by", "updated_at"])
    log(
        AuditAction.RESTRUCTURE,
        _("Loan %(reference)s restructured into %(new_reference)s for %(amount)s MXN") % {
            "reference": loan.reference, "new_reference": new_loan.reference,
            "amount": balance,
        },
        target=loan, user=user,
        data={"restructured_balance": str(balance), "new_reference": new_loan.reference},
    )
    return new_loan


# --------------------------------------------------------------------------
# Derived balances and statuses
# --------------------------------------------------------------------------
@transaction.atomic
def recalculate_loan(loan: Loan) -> Loan:
    """Rebuild installments and balances from the confirmed payment allocations.

    This function is the consistency guarantee of the system: the balance
    never depends on running totals, it can always be recomputed.
    """
    from apps.payments.models import PaymentAllocation, PaymentStatus

    allocations = (
        PaymentAllocation.objects.filter(
            installment__loan=loan, payment__status=PaymentStatus.CONFIRMED
        )
        .values("installment_id")
        .annotate(
            amount=Sum("amount"),
            principal=Sum("principal"),
            interest=Sum("interest"),
        )
    )
    by_installment = {row["installment_id"]: row for row in allocations}

    total_principal = ZERO
    total_interest = ZERO
    today = today_local()
    for installment in loan.installments.all():
        row = by_installment.get(installment.pk)
        installment.amount_paid = money(row["amount"]) if row else ZERO
        installment.principal_paid = money(row["principal"]) if row else ZERO
        installment.interest_paid = money(row["interest"]) if row else ZERO
        total_principal += installment.principal_paid
        total_interest += installment.interest_paid
        installment.status = _installment_status(installment, today)
        if installment.status != InstallmentStatus.PAID:
            installment.settled_on = None
        elif installment.settled_on is None:
            installment.settled_on = today
        installment.save(update_fields=["amount_paid", "principal_paid", "interest_paid",
                                        "status", "settled_on"])

    loan.principal_paid = money(total_principal)
    loan.interest_paid = money(total_interest)
    loan.outstanding_balance = max(
        money(loan.total_payable - total_principal - total_interest), ZERO
    )
    loan.save(update_fields=["principal_paid", "interest_paid", "outstanding_balance",
                             "updated_at"])
    refresh_status(loan)
    return loan


def _installment_status(installment: Installment, today: dt.date) -> str:
    if installment.amount_paid >= installment.scheduled_amount:
        return InstallmentStatus.PAID
    is_overdue = installment.due_date < today
    if installment.amount_paid > ZERO:
        return InstallmentStatus.OVERDUE if is_overdue else InstallmentStatus.PARTIAL
    return InstallmentStatus.OVERDUE if is_overdue else InstallmentStatus.PENDING


def refresh_status(loan: Loan) -> str:
    """Derive the operational status of the loan from its installments.

    Cancelled and restructured loans are left alone.
    """
    if loan.status in (LoanStatus.CANCELLED, LoanStatus.RESTRUCTURED):
        return loan.status

    new_status = LoanStatus.ACTIVE
    if loan.outstanding_balance <= ZERO:
        new_status = LoanStatus.SETTLED
    else:
        grace_days = loan.business.grace_days
        cutoff = today_local() - dt.timedelta(days=grace_days)
        has_overdue = (
            loan.installments.filter(due_date__lt=cutoff)
            .exclude(status=InstallmentStatus.PAID)
            .exists()
        )
        if has_overdue:
            new_status = LoanStatus.PAST_DUE

    if new_status != loan.status:
        previous = loan.status
        loan.status = new_status
        loan.save(update_fields=["status", "updated_at"])
        if new_status == LoanStatus.SETTLED:
            log(
                AuditAction.UPDATE,
                _("Loan %(reference)s settled (previous status: %(previous)s)") % {
                    "reference": loan.reference,
                    "previous": dict(LoanStatus.choices).get(previous, previous),
                },
                target=loan,
            )
    return loan.status


def refresh_statuses(queryset=None) -> int:
    """Walk the live loans and refresh their status (past due / settled)."""
    queryset = queryset if queryset is not None else Loan.objects.live()
    changed = 0
    for loan in queryset.select_related("business"):
        previous = loan.status
        if refresh_status(loan) != previous:
            changed += 1
    return changed


def pre_loan_summary(customer) -> dict:
    """Information shown BEFORE granting a new loan.

    It is not an automatic approval or rejection: it is data for a person
    to decide with.
    """
    from apps.customers.services import customer_summary

    summary = customer_summary(customer)
    summary["live_loans"] = list(
        customer.loans.live().order_by("disbursement_date")
    )
    summary["warnings"] = []
    if summary["outstanding_balance"] > ZERO:
        summary["warnings"].append(
            _("The customer owes %(amount)s MXN.") % {
                "amount": money(summary["outstanding_balance"])}
        )
    if summary["overdue_installments"]:
        summary["warnings"].append(
            _("They have %(count)s unpaid overdue installment(s).") % {
                "count": summary["overdue_installments"]}
        )
    if customer.is_restricted:
        summary["warnings"].append(_("The customer is flagged as RESTRICTED."))
    return summary


def interest_per_thousand(rate) -> Decimal:
    """Presentation helper: how much interest corresponds to 1,000 MXN."""
    return money(to_decimal(rate) * 1000)
