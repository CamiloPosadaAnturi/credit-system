"""Businesses / branches and their commercial configuration."""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.choices import InterestMode, PaymentFrequency, RatePeriod
from apps.core.mexican_states import MEXICAN_STATES
from apps.core.models import BaseModel
from apps.core.validators import validate_phone, validate_tax_id


class BusinessQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class Business(BaseModel):
    """A business or branch that grants loans.

    Each business isolates its own data: customers, loans, payments and
    portfolio always belong to one business and are never mixed.
    """

    trade_name = models.CharField(_("trade name"), max_length=150)
    legal_name = models.CharField(_("legal name"), max_length=200, blank=True)
    tax_id = models.CharField(_("RFC"), max_length=13, blank=True,
                              validators=[validate_tax_id])
    phone = models.CharField(_("phone"), max_length=20, blank=True,
                             validators=[validate_phone])
    email = models.EmailField(_("email"), blank=True)
    address = models.CharField(_("address"), max_length=255, blank=True)
    city = models.CharField(_("city"), max_length=100, blank=True)
    state = models.CharField(_("state"), max_length=5, choices=MEXICAN_STATES, blank=True)
    manager = models.ForeignKey(
        "users.User",
        verbose_name=_("person in charge"),
        on_delete=models.PROTECT,
        related_name="managed_businesses",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(_("active"), default=True)

    # --- Default interest configuration -----------------------------------
    interest_mode = models.CharField(
        _("interest mode"),
        max_length=20,
        choices=InterestMode.choices,
        default=InterestMode.FLAT_ON_PRINCIPAL,
    )
    interest_rate = models.DecimalField(
        _("interest rate"),
        max_digits=7,
        decimal_places=4,
        default=Decimal("0.4000"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Expressed as a ratio. 0.4000 = 40% (400 MXN per 1,000 MXN)."),
    )
    rate_period = models.CharField(
        _("rate period"),
        max_length=15,
        choices=RatePeriod.choices,
        default=RatePeriod.CONTRACT,
        help_text=_("Contractual period the rate refers to. It must match the contract."),
    )
    payment_frequency = models.CharField(
        _("default payment frequency"),
        max_length=15,
        choices=PaymentFrequency.choices,
        default=PaymentFrequency.WEEKLY,
    )
    installment_count = models.PositiveIntegerField(
        _("default number of installments"), default=4,
        validators=[MinValueValidator(1)],
    )

    # --- Late payment configuration ---------------------------------------
    grace_days = models.PositiveIntegerField(
        _("grace days"), default=0,
        help_text=_("Days after the due date before an installment counts as overdue."),
    )
    charges_late_fee = models.BooleanField(
        _("charges late fees"), default=False,
        help_text=_("When off, the system never adds late charges. Turn it on only "
                    "with a documented and authorized policy."),
    )
    late_fee_rate = models.DecimalField(
        _("daily late fee rate"), max_digits=7, decimal_places=4, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Ratio applied to the overdue balance, per day past due."),
    )
    allows_early_payoff = models.BooleanField(_("allows early payoff"), default=True)
    early_payoff_discount = models.DecimalField(
        _("early payoff discount"), max_digits=7, decimal_places=4,
        default=Decimal("0"),
        help_text=_("Ratio discounted from the UNEARNED interest. "
                    "0 = the full contractual balance is charged."),
    )

    notes = models.TextField(_("notes"), blank=True)

    objects = BusinessQuerySet.as_manager()

    class Meta:
        verbose_name = _("business")
        verbose_name_plural = _("businesses")
        ordering = ["trade_name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(interest_rate__gte=0),
                name="business_rate_not_negative"),
            models.CheckConstraint(
                condition=models.Q(installment_count__gte=1),
                name="business_min_one_installment"),
        ]

    def __str__(self) -> str:
        return self.trade_name

    def get_absolute_url(self) -> str:
        return reverse("businesses:detail", args=[self.pk])

    @property
    def rate_percentage(self) -> Decimal:
        return (self.interest_rate * 100).quantize(Decimal("0.01"))

    @property
    def interest_per_thousand(self) -> Decimal:
        """How much interest is charged per 1,000 MXN lent."""
        return (self.interest_rate * 1000).quantize(Decimal("0.01"))

    def current_interest_rule(self) -> dict:
        """Snapshot of the active rule, frozen into every loan."""
        return {
            "interest_mode": self.interest_mode,
            "interest_rate": self.interest_rate,
            "rate_period": self.rate_period,
        }
