"""Registering and allocating payments.

Allocation policy (configurable, see docs/reglas_financieras.md):

1. A payment is applied first to the OLDEST OVERDUE installments and then
   to the following ones by due date.
2. Within each installment the scheduled INTEREST is covered first and the
   PRINCIPAL afterwards. This creates no new interest: it only splits what
   was already agreed.
3. The split is stored in ``PaymentAllocation``, so the balance can always
   be rebuilt from scratch.

Every operation is atomic and locks the loan (``select_for_update``) to
avoid inconsistencies caused by simultaneous payments.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.audit.models import AuditAction
from apps.audit.services import log
from apps.core.errors import PaymentError
from apps.core.money import ZERO, money, to_decimal
from apps.loans.models import LIVE_STATUSES, Installment, InstallmentStatus, Loan
from apps.loans.services import recalculate_loan
from apps.payments.models import (
    Payment,
    PaymentAllocation,
    PaymentKind,
    PaymentMethod,
    PaymentStatus,
)

#: Seconds within which an identical payment is treated as a duplicate.
DUPLICATE_WINDOW_SECONDS = 120


def generate_payment_reference(business) -> str:
    year = timezone.localdate().year
    prefix = f"PY-{business.pk:03d}-{year}-"
    last = (
        Payment.objects.filter(reference__startswith=prefix)
        .order_by("-reference")
        .values_list("reference", flat=True)
        .first()
    )
    sequence = int(last.split("-")[-1]) + 1 if last else 1
    return f"{prefix}{sequence:05d}"


def outstanding_balance(loan: Loan) -> Decimal:
    """What the customer still owes for the whole contract."""
    return money(loan.outstanding_balance)


def overdue_balance(loan: Loan, today: dt.date | None = None) -> Decimal:
    from apps.core.dates import today_local

    today = today or today_local()
    total = ZERO
    for installment in loan.installments.filter(due_date__lt=today).exclude(
        status=InstallmentStatus.PAID
    ):
        total += installment.balance
    return money(total)


@transaction.atomic
def register_payment(
    *,
    loan: Loan,
    amount,
    user,
    method: str = PaymentMethod.CASH,
    paid_at=None,
    collector=None,
    external_reference: str = "",
    notes: str = "",
    idempotency_key: str = "",
    allow_overpayment: bool = False,
    kind: str = PaymentKind.PAYMENT,
    force_duplicate: bool = False,
) -> Payment:
    """Register a payment and allocate it to the loan installments."""
    amount = money(to_decimal(amount))
    if amount <= ZERO:
        raise PaymentError(_("The payment amount must be greater than zero."))

    if idempotency_key:
        existing = Payment.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            # The form was submitted twice: return the original payment.
            return existing

    loan = Loan.objects.select_for_update().get(pk=loan.pk)
    if loan.status not in LIVE_STATUSES:
        raise PaymentError(
            _("Payments cannot be registered on a %(status)s loan.") % {
                "status": loan.get_status_display()}
        )

    paid_at = paid_at or timezone.now()
    if not force_duplicate:
        _check_duplicate(loan, amount, paid_at)

    payable = outstanding_balance(loan)
    if amount > payable and not allow_overpayment:
        raise PaymentError(
            _("The amount (%(amount)s MXN) is larger than the outstanding balance "
              "(%(balance)s MXN). Authorize the overpayment or register a payoff.") % {
                "amount": amount, "balance": payable}
        )

    payment = Payment.objects.create(
        reference=generate_payment_reference(loan.business),
        loan=loan,
        customer=loan.customer,
        business=loan.business,
        paid_at=paid_at,
        amount=amount,
        method=method,
        kind=kind,
        status=PaymentStatus.CONFIRMED,
        received_by=user,
        collector=collector or loan.collector,
        external_reference=external_reference,
        notes=notes,
        idempotency_key=idempotency_key,
    )

    allocated, overpayment = allocate_payment(payment, loan)
    payment.allocated_amount = allocated
    payment.overpayment = overpayment
    payment.save(update_fields=["allocated_amount", "overpayment"])

    recalculate_loan(loan)

    log(
        AuditAction.PAYMENT,
        _("Payment %(reference)s of %(amount)s MXN applied to %(loan)s") % {
            "reference": payment.reference, "amount": amount, "loan": loan.reference,
        },
        target=payment, user=user, business=loan.business,
        data={"loan": loan.reference, "amount": str(amount),
              "allocated": str(allocated), "overpayment": str(overpayment),
              "method": method, "kind": kind},
    )
    _notify_if_settled(loan)
    return payment


def _check_duplicate(loan: Loan, amount: Decimal, paid_at) -> None:
    cutoff = paid_at - dt.timedelta(seconds=DUPLICATE_WINDOW_SECONDS)
    duplicate = Payment.objects.filter(
        loan=loan, amount=amount, status=PaymentStatus.CONFIRMED,
        paid_at__gte=cutoff, paid_at__lte=paid_at,
    ).exists()
    if duplicate:
        raise PaymentError(
            _("An identical payment was registered less than two minutes ago. "
              "If these really are two separate payments, tick the confirmation box.")
        )


def allocate_payment(payment: Payment, loan: Loan | None = None) -> tuple[Decimal, Decimal]:
    """Split the payment amount across the pending installments.

    Returns ``(allocated_amount, overpayment)``.
    """
    loan = loan or payment.loan
    remaining = money(payment.amount)
    allocated = ZERO

    installments = list(
        Installment.objects.select_for_update()
        .filter(loan=loan)
        .exclude(status=InstallmentStatus.PAID)
        .order_by("due_date", "number")
    )

    for installment in installments:
        if remaining <= ZERO:
            break
        installment_balance = money(installment.balance)
        if installment_balance <= ZERO:
            continue
        to_apply = min(installment_balance, remaining)
        # Within the installment: interest first, then principal.
        interest = min(money(installment.interest_balance), to_apply)
        principal = money(to_apply - interest)
        PaymentAllocation.objects.create(
            payment=payment, installment=installment, amount=to_apply,
            principal=principal, interest=interest,
        )
        remaining = money(remaining - to_apply)
        allocated = money(allocated + to_apply)

    return allocated, money(remaining)


@transaction.atomic
def reverse_payment(payment: Payment, user, reason: str) -> Payment:
    """Reverse a confirmed payment. The original record is NEVER deleted."""
    if not reason:
        raise PaymentError(_("You must state the reason for the reversal."))
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.status != PaymentStatus.CONFIRMED:
        raise PaymentError(_("Only a confirmed payment can be reversed."))

    payment.status = PaymentStatus.REVERSED
    payment.reversal_reason = reason
    payment.reversed_by = user
    payment.reversed_at = timezone.now()
    payment.save(update_fields=["status", "reversal_reason", "reversed_by",
                                "reversed_at"])

    loan = Loan.objects.select_for_update().get(pk=payment.loan_id)
    # recalculate_loan recomputes the balance from the confirmed allocations
    # and moves the loan back to 'active' or 'past_due' if it owes again.
    recalculate_loan(loan)

    log(
        AuditAction.REVERSAL,
        _("Payment %(reference)s reversed (%(amount)s MXN): %(reason)s") % {
            "reference": payment.reference, "amount": payment.amount, "reason": reason,
        },
        target=payment, user=user, business=payment.business,
        data={"loan": loan.reference, "amount": str(payment.amount), "reason": reason},
    )
    return payment


# --------------------------------------------------------------------------
# Early payoff
# --------------------------------------------------------------------------
def early_payoff_quote(loan: Loan) -> dict:
    """How much the customer would pay today to settle the loan.

    If the business configured a discount on the UNEARNED interest
    (installments not yet due), it is applied here. With a discount of 0
    the customer pays the full contractual balance.
    """
    from apps.core.dates import today_local

    today = today_local()
    balance = outstanding_balance(loan)
    unearned_interest = ZERO
    for installment in loan.installments.filter(due_date__gt=today).exclude(
        status=InstallmentStatus.PAID
    ):
        unearned_interest += installment.interest_balance

    discount_rate = to_decimal(loan.business.early_payoff_discount)
    discount = money(unearned_interest * discount_rate)
    return {
        "contractual_balance": balance,
        "unearned_interest": money(unearned_interest),
        "discount_rate": discount_rate,
        "discount": discount,
        "payoff_amount": money(balance - discount),
        "allowed": loan.business.allows_early_payoff,
    }


@transaction.atomic
def settle_early(
    loan: Loan, user, *, method: str = PaymentMethod.CASH,
    external_reference: str = "", notes: str = "", idempotency_key: str = "",
) -> Payment:
    """Register the payoff payment and, if any, the authorized write-off."""
    quote = early_payoff_quote(loan)
    if not quote["allowed"]:
        raise PaymentError(_("This business does not allow early payoff."))
    if quote["payoff_amount"] <= ZERO:
        raise PaymentError(_("The loan has no balance left to settle."))

    payment = register_payment(
        loan=loan,
        amount=quote["payoff_amount"],
        user=user,
        method=method,
        external_reference=external_reference,
        notes=notes or _("Early payoff"),
        idempotency_key=idempotency_key,
        force_duplicate=True,
    )

    if quote["discount"] > ZERO:
        register_payment(
            loan=loan,
            amount=quote["discount"],
            user=user,
            method=PaymentMethod.OTHER,
            kind=PaymentKind.WRITE_OFF,
            notes=_("Authorized write-off for the early payoff of %(reference)s "
                    "(discount on unearned interest)") % {"reference": loan.reference},
            force_duplicate=True,
        )
    return payment


def _notify_if_settled(loan: Loan) -> None:
    from apps.loans.models import LoanStatus

    loan.refresh_from_db(fields=["status"])
    if loan.status == LoanStatus.SETTLED:
        from apps.notifications.services import create_notification

        create_notification(
            business=loan.business,
            title=_("Loan %(reference)s settled") % {"reference": loan.reference},
            message=_("%(customer)s settled their loan of %(amount)s MXN.") % {
                "customer": loan.customer, "amount": loan.principal,
            },
            url=loan.get_absolute_url(),
        )
