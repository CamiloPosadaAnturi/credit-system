"""Loans and their installment schedule.

Key rules (see docs/reglas_financieras.md):

* Interest is computed ONCE, when the loan is approved, on the initial
  principal. There is no compounding and no recalculation per payment.
* The business interest rule is copied onto the loan (snapshot), so
  changing the business rate never alters loans already approved.
* ``outstanding_balance`` is a derived field: it can always be rebuilt
  from the payment allocations (``apps.payments.models.PaymentAllocation``).
"""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.choices import InterestMode, PaymentFrequency, RatePeriod
from apps.core.models import BaseModel
from apps.core.money import ZERO


class LoanStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    PENDING = "pending_approval", _("Pending approval")
    APPROVED = "approved", _("Approved")
    DISBURSED = "disbursed", _("Disbursed")
    ACTIVE = "active", _("Active")
    PAST_DUE = "past_due", _("Past due")
    SETTLED = "settled", _("Settled")
    CANCELLED = "cancelled", _("Cancelled")
    RESTRUCTURED = "restructured", _("Restructured")


#: Statuses where the loan still has a collectable balance.
LIVE_STATUSES = [
    LoanStatus.DISBURSED,
    LoanStatus.ACTIVE,
    LoanStatus.PAST_DUE,
]
#: Statuses where the money already left the business.
DISBURSED_STATUSES = LIVE_STATUSES + [
    LoanStatus.SETTLED,
    LoanStatus.RESTRUCTURED,
]
#: Statuses before disbursement: the loan terms can still be edited.
EDITABLE_STATUSES = [LoanStatus.DRAFT, LoanStatus.PENDING]


class InstallmentStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    PARTIAL = "partial", _("Partially paid")
    PAID = "paid", _("Paid")
    OVERDUE = "overdue", _("Overdue")


class LoanQuerySet(models.QuerySet):
    def live(self):
        return self.filter(status__in=LIVE_STATUSES)

    def disbursed(self):
        return self.filter(status__in=DISBURSED_STATUSES)

    def settled(self):
        return self.filter(status=LoanStatus.SETTLED)

    def past_due(self):
        return self.filter(status=LoanStatus.PAST_DUE)

    def of_business(self, business):
        return self.filter(business=business)


class Loan(BaseModel):
    reference = models.CharField(_("reference"), max_length=30, unique=True,
                                 editable=False)
    customer = models.ForeignKey(
        "customers.Customer", verbose_name=_("customer"), on_delete=models.PROTECT,
        related_name="loans",
    )
    business = models.ForeignKey(
        "businesses.Business", verbose_name=_("business"), on_delete=models.PROTECT,
        related_name="loans",
    )
    collector = models.ForeignKey(
        "users.User", verbose_name=_("assigned collector"), on_delete=models.SET_NULL,
        null=True, blank=True, related_name="assigned_loans",
        limit_choices_to={"role": "collector"},
    )

    application_date = models.DateField(_("application date"))
    approval_date = models.DateField(_("approval date"), null=True, blank=True)
    disbursement_date = models.DateField(_("disbursement date"), null=True, blank=True)

    principal = models.DecimalField(
        _("principal"), max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    # --- Snapshot of the applied interest rule ----------------------------
    interest_mode = models.CharField(
        _("interest mode"), max_length=20, choices=InterestMode.choices,
        default=InterestMode.FLAT_ON_PRINCIPAL,
    )
    interest_rate = models.DecimalField(
        _("applied interest rate"), max_digits=7, decimal_places=4,
        default=Decimal("0.4000"),
        help_text=_("Ratio frozen when the loan was approved."),
    )
    rate_period = models.CharField(
        _("rate period"), max_length=15, choices=RatePeriod.choices,
        default=RatePeriod.CONTRACT,
    )

    total_interest = models.DecimalField(
        _("total interest"), max_digits=12, decimal_places=2, default=ZERO)
    total_payable = models.DecimalField(
        _("total payable"), max_digits=12, decimal_places=2, default=ZERO)

    payment_frequency = models.CharField(
        _("payment frequency"), max_length=15, choices=PaymentFrequency.choices,
        default=PaymentFrequency.WEEKLY,
    )
    custom_days = models.PositiveIntegerField(
        _("days between installments"), null=True, blank=True,
        help_text=_("Only for the custom frequency."),
    )
    installment_count = models.PositiveIntegerField(
        _("number of installments"), default=1, validators=[MinValueValidator(1)])
    installment_amount = models.DecimalField(
        _("installment amount"), max_digits=12, decimal_places=2, default=ZERO)

    first_payment_date = models.DateField(_("first payment date"))
    final_due_date = models.DateField(_("final due date"), null=True, blank=True)

    # --- Derived balances (rebuilt from the payment allocations) ----------
    principal_paid = models.DecimalField(
        _("principal paid"), max_digits=12, decimal_places=2, default=ZERO)
    interest_paid = models.DecimalField(
        _("interest paid"), max_digits=12, decimal_places=2, default=ZERO)
    outstanding_balance = models.DecimalField(
        _("outstanding balance"), max_digits=12, decimal_places=2, default=ZERO)

    status = models.CharField(
        _("status"), max_length=25, choices=LoanStatus.choices,
        default=LoanStatus.DRAFT, db_index=True,
    )
    cancellation_reason = models.CharField(_("cancellation reason"), max_length=255,
                                           blank=True)
    original_loan = models.ForeignKey(
        "self", verbose_name=_("restructured loan"), on_delete=models.SET_NULL,
        null=True, blank=True, related_name="restructurings",
    )
    notes = models.TextField(_("notes"), blank=True)
    contract = models.FileField(
        _("contract or document"), upload_to="contracts/%Y/%m/", blank=True, null=True)

    approved_by = models.ForeignKey(
        "users.User", verbose_name=_("approved by"), on_delete=models.SET_NULL,
        null=True, blank=True, related_name="approved_loans",
    )
    disbursed_by = models.ForeignKey(
        "users.User", verbose_name=_("disbursed by"), on_delete=models.SET_NULL,
        null=True, blank=True, related_name="disbursed_loans",
    )

    objects = LoanQuerySet.as_manager()

    class Meta:
        verbose_name = _("loan")
        verbose_name_plural = _("loans")
        ordering = ["-application_date", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(principal__gt=0), name="loan_principal_positive"),
            models.CheckConstraint(
                condition=Q(total_interest__gte=0), name="loan_interest_not_negative"),
            models.CheckConstraint(
                condition=Q(installment_count__gte=1), name="loan_min_one_installment"),
            models.CheckConstraint(
                condition=Q(outstanding_balance__gte=0), name="loan_balance_not_negative"),
        ]
        indexes = [
            models.Index(fields=["business", "status"]),
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["collector", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.reference} - {self.customer}"

    def get_absolute_url(self) -> str:
        return reverse("loans:detail", args=[self.pk])

    # --- Read-only properties --------------------------------------------
    @property
    def total_paid(self) -> Decimal:
        return self.principal_paid + self.interest_paid

    @property
    def is_live(self) -> bool:
        return self.status in LIVE_STATUSES

    @property
    def is_editable(self) -> bool:
        """A disbursed loan is never edited: it is adjusted with audited operations."""
        return self.status in EDITABLE_STATUSES

    @property
    def percent_paid(self) -> Decimal:
        if not self.total_payable:
            return ZERO
        return (self.total_paid * 100 / self.total_payable).quantize(Decimal("0.01"))

    @property
    def interest_per_thousand(self) -> Decimal:
        return (self.interest_rate * 1000).quantize(Decimal("0.01"))

    def overdue_installments(self):
        from apps.core.dates import today_local

        return self.installments.filter(
            due_date__lt=today_local()
        ).exclude(status=InstallmentStatus.PAID)

    @property
    def overdue_balance(self) -> Decimal:
        total = ZERO
        for installment in self.overdue_installments():
            total += installment.balance
        return total

    @property
    def days_past_due(self) -> int:
        """Days past due of the loan = those of its oldest overdue installment."""
        installment = self.overdue_installments().order_by("due_date").first()
        return installment.days_past_due if installment else 0

    @property
    def next_installment(self):
        return (
            self.installments.exclude(status=InstallmentStatus.PAID)
            .order_by("due_date")
            .first()
        )


class Installment(models.Model):
    """One line of the loan's payment schedule."""

    loan = models.ForeignKey(
        Loan, verbose_name=_("loan"), on_delete=models.CASCADE,
        related_name="installments")
    number = models.PositiveIntegerField(_("installment number"))
    due_date = models.DateField(_("due date"), db_index=True)
    scheduled_amount = models.DecimalField(
        _("scheduled amount"), max_digits=12, decimal_places=2)
    scheduled_principal = models.DecimalField(
        _("scheduled principal"), max_digits=12, decimal_places=2, default=ZERO)
    scheduled_interest = models.DecimalField(
        _("scheduled interest"), max_digits=12, decimal_places=2, default=ZERO)
    amount_paid = models.DecimalField(
        _("amount paid"), max_digits=12, decimal_places=2, default=ZERO)
    principal_paid = models.DecimalField(
        _("principal paid"), max_digits=12, decimal_places=2, default=ZERO)
    interest_paid = models.DecimalField(
        _("interest paid"), max_digits=12, decimal_places=2, default=ZERO)
    status = models.CharField(
        _("status"), max_length=12, choices=InstallmentStatus.choices,
        default=InstallmentStatus.PENDING, db_index=True)
    settled_on = models.DateField(_("settled on"), null=True, blank=True)

    class Meta:
        verbose_name = _("installment")
        verbose_name_plural = _("installments")
        ordering = ["loan", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["loan", "number"], name="installment_number_unique_per_loan"),
            models.CheckConstraint(
                condition=Q(scheduled_amount__gte=0),
                name="installment_amount_not_negative"),
        ]

    def __str__(self) -> str:
        return f"Installment {self.number}/{self.loan.installment_count} " \
               f"of {self.loan.reference}"

    @property
    def balance(self) -> Decimal:
        return self.scheduled_amount - self.amount_paid

    @property
    def principal_balance(self) -> Decimal:
        return self.scheduled_principal - self.principal_paid

    @property
    def interest_balance(self) -> Decimal:
        return self.scheduled_interest - self.interest_paid

    @property
    def is_paid(self) -> bool:
        return self.balance <= ZERO

    @property
    def days_past_due(self) -> int:
        from apps.core.dates import today_local

        if self.is_paid:
            return 0
        days = (today_local() - self.due_date).days
        return max(days, 0)

    def days_past_due_with_grace(self, grace_days: int = 0) -> int:
        return max(self.days_past_due - grace_days, 0)
