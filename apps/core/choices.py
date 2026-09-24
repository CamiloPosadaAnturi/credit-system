"""Catalogs shared between businesses and loans."""
from django.db import models
from django.utils.translation import gettext_lazy as _


class PaymentFrequency(models.TextChoices):
    DAILY = "daily", _("Daily")
    WEEKLY = "weekly", _("Weekly")
    BIWEEKLY = "biweekly", _("Biweekly (every 15 days)")
    MONTHLY = "monthly", _("Monthly")
    CUSTOM = "custom", _("Custom (every N days)")


#: Calendar days between installments for each frequency.
#: ``monthly`` is computed by calendar, not by a fixed number of days.
DAYS_PER_FREQUENCY = {
    PaymentFrequency.DAILY: 1,
    PaymentFrequency.WEEKLY: 7,
    PaymentFrequency.BIWEEKLY: 15,
}


class InterestMode(models.TextChoices):
    FLAT_ON_PRINCIPAL = "flat_on_principal", _("Flat interest on principal (rate x principal)")
    SIMPLE_PER_PERIOD = "simple_per_period", _(
        "Simple interest per period (rate x principal x installments)")
    NO_INTEREST = "no_interest", _("No interest")


class RatePeriod(models.TextChoices):
    """Contractual period the configured rate refers to.

    IMPORTANT: the system does NOT assume the rate is monthly or annual.
    The period must be explicit here and in the loan contract.
    """

    CONTRACT = "contract", _("For the whole contract term")
    DAILY = "daily", _("Per day")
    WEEKLY = "weekly", _("Per week")
    BIWEEKLY = "biweekly", _("Per fortnight")
    MONTHLY = "monthly", _("Per month")
