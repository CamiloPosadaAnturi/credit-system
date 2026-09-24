"""Payments, write-offs and how they are allocated to installments.

Design:

* ``Payment`` is the economic fact: the money the customer handed over.
* ``PaymentAllocation`` is the detail of HOW that money was split across
  installments, separating principal and interest. It is the source of
  truth used to rebuild a loan's balance at any time.
* A confirmed payment is NEVER deleted or edited: it is reversed, and the
  reversal keeps its reason and its author.
"""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.money import ZERO


class PaymentMethod(models.TextChoices):
    CASH = "cash", _("Cash")
    TRANSFER = "transfer", _("Bank transfer")
    DEPOSIT = "deposit", _("Deposit")
    OTHER = "other", _("Other")


class PaymentStatus(models.TextChoices):
    CONFIRMED = "confirmed", _("Confirmed")
    REVERSED = "reversed", _("Reversed")


class PaymentKind(models.TextChoices):
    PAYMENT = "payment", _("Customer payment")
    WRITE_OFF = "write_off", _("Authorized write-off / discount")


class PaymentQuerySet(models.QuerySet):
    def confirmed(self):
        return self.filter(status=PaymentStatus.CONFIRMED)

    def cash_received(self):
        """Only money actually received (write-offs excluded)."""
        return self.confirmed().filter(kind=PaymentKind.PAYMENT)

    def on_day(self, date):
        return self.filter(paid_at__date=date)


class Payment(models.Model):
    reference = models.CharField(_("reference"), max_length=30, unique=True,
                                 editable=False)
    loan = models.ForeignKey(
        "loans.Loan", verbose_name=_("loan"), on_delete=models.PROTECT,
        related_name="payments")
    customer = models.ForeignKey(
        "customers.Customer", verbose_name=_("customer"), on_delete=models.PROTECT,
        related_name="payments")
    business = models.ForeignKey(
        "businesses.Business", verbose_name=_("business"), on_delete=models.PROTECT,
        related_name="payments")

    paid_at = models.DateTimeField(_("payment date and time"), db_index=True)
    amount = models.DecimalField(
        _("amount received"), max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))])
    allocated_amount = models.DecimalField(
        _("amount allocated to installments"), max_digits=12, decimal_places=2,
        default=ZERO)
    overpayment = models.DecimalField(
        _("unallocated overpayment"), max_digits=12, decimal_places=2, default=ZERO,
        help_text=_("Only allowed with an explicit authorization when registering."))

    method = models.CharField(
        _("payment method"), max_length=15, choices=PaymentMethod.choices,
        default=PaymentMethod.CASH)
    kind = models.CharField(
        _("kind"), max_length=15, choices=PaymentKind.choices,
        default=PaymentKind.PAYMENT)
    status = models.CharField(
        _("status"), max_length=12, choices=PaymentStatus.choices,
        default=PaymentStatus.CONFIRMED, db_index=True)

    received_by = models.ForeignKey(
        "users.User", verbose_name=_("registered by"), on_delete=models.PROTECT,
        related_name="received_payments")
    collector = models.ForeignKey(
        "users.User", verbose_name=_("collector"), on_delete=models.SET_NULL,
        null=True, blank=True, related_name="collected_payments")

    external_reference = models.CharField(_("transaction reference"), max_length=80,
                                          blank=True)
    notes = models.TextField(_("notes"), blank=True)

    idempotency_key = models.CharField(
        _("idempotency key"), max_length=64, blank=True,
        help_text=_("Prevents the same form from registering the payment twice."))

    # --- Reversal ---------------------------------------------------------
    reversal_reason = models.CharField(_("reversal reason"), max_length=255, blank=True)
    reversed_by = models.ForeignKey(
        "users.User", verbose_name=_("reversed by"), on_delete=models.SET_NULL,
        null=True, blank=True, related_name="reversed_payments")
    reversed_at = models.DateTimeField(_("reversal date"), null=True, blank=True)

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    objects = PaymentQuerySet.as_manager()

    class Meta:
        verbose_name = _("payment")
        verbose_name_plural = _("payments")
        ordering = ["-paid_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0),
                                   name="payment_amount_positive"),
            models.CheckConstraint(condition=Q(overpayment__gte=0),
                                   name="payment_overpayment_not_negative"),
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="payment_idempotency_key_unique"),
        ]
        indexes = [
            models.Index(fields=["business", "status", "-paid_at"]),
            models.Index(fields=["loan", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.reference} - {self.amount} MXN"

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("payments:detail", args=[self.pk])

    @property
    def is_confirmed(self) -> bool:
        return self.status == PaymentStatus.CONFIRMED

    @property
    def is_write_off(self) -> bool:
        return self.kind == PaymentKind.WRITE_OFF


class PaymentAllocation(models.Model):
    """How one payment was applied to one installment.

    Storing this split makes it possible to rebuild the loan balance line
    by line, without relying on running totals.
    """

    payment = models.ForeignKey(
        Payment, verbose_name=_("payment"), on_delete=models.CASCADE,
        related_name="allocations")
    installment = models.ForeignKey(
        "loans.Installment", verbose_name=_("installment"), on_delete=models.PROTECT,
        related_name="allocations")
    amount = models.DecimalField(_("allocated amount"), max_digits=12, decimal_places=2)
    principal = models.DecimalField(_("principal"), max_digits=12, decimal_places=2,
                                    default=ZERO)
    interest = models.DecimalField(_("interest"), max_digits=12, decimal_places=2,
                                   default=ZERO)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("payment allocation")
        verbose_name_plural = _("payment allocations")
        ordering = ["payment", "installment__number"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="allocation_amount_positive"),
        ]

    def __str__(self) -> str:
        return (f"{self.payment.reference} -> installment "
                f"{self.installment.number}: {self.amount}")
