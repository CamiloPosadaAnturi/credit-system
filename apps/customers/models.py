"""Customers of a business and their personal references."""
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.mexican_states import MEXICAN_STATES
from apps.core.models import BaseModel
from apps.core.validators import (
    validate_national_id,
    validate_phone,
    validate_postal_code,
    validate_tax_id,
)


class CustomerStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    INACTIVE = "inactive", _("Inactive")
    RESTRICTED = "restricted", _("Restricted")


class CustomerQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=CustomerStatus.ACTIVE)

    def of_business(self, business):
        return self.filter(business=business)

    def search(self, term: str):
        if not term:
            return self
        return self.filter(
            Q(first_name__icontains=term)
            | Q(last_name__icontains=term)
            | Q(second_last_name__icontains=term)
            | Q(phone__icontains=term)
            | Q(code__icontains=term)
        )


class Customer(BaseModel):
    """A person who receives loans from a business.

    Data protection: the national ID (CURP) and tax ID (RFC) are optional
    and only shown to roles holding ``view_sensitive_data``. No personal
    data beyond what the operation requires is stored.
    """

    business = models.ForeignKey(
        "businesses.Business", verbose_name=_("business"), on_delete=models.PROTECT,
        related_name="customers",
    )
    code = models.CharField(
        _("code"), max_length=20, blank=True,
        help_text=_("Internal identifier of the customer within the business."),
    )
    first_name = models.CharField(_("first name(s)"), max_length=100)
    last_name = models.CharField(_("last name"), max_length=80)
    second_last_name = models.CharField(_("second last name"), max_length=80, blank=True)

    national_id = models.CharField(_("CURP"), max_length=18, blank=True,
                                   validators=[validate_national_id])
    tax_id = models.CharField(_("RFC"), max_length=13, blank=True,
                              validators=[validate_tax_id])
    birth_date = models.DateField(_("date of birth"), null=True, blank=True)

    phone = models.CharField(_("primary phone"), max_length=20,
                             validators=[validate_phone])
    alt_phone = models.CharField(_("alternate phone"), max_length=20, blank=True,
                                 validators=[validate_phone])
    email = models.EmailField(_("email"), blank=True)

    address = models.CharField(_("address"), max_length=255, blank=True)
    city = models.CharField(_("city"), max_length=100, blank=True)
    state = models.CharField(_("state"), max_length=5, choices=MEXICAN_STATES, blank=True)
    postal_code = models.CharField(_("postal code"), max_length=5, blank=True,
                                   validators=[validate_postal_code])

    occupation = models.CharField(_("occupation"), max_length=120, blank=True)

    collector = models.ForeignKey(
        "users.User", verbose_name=_("assigned collector"), on_delete=models.SET_NULL,
        null=True, blank=True, related_name="assigned_customers",
        limit_choices_to={"role": "collector"},
    )
    status = models.CharField(
        _("status"), max_length=15, choices=CustomerStatus.choices,
        default=CustomerStatus.ACTIVE)
    notes = models.TextField(_("internal notes"), blank=True)

    objects = CustomerQuerySet.as_manager()

    class Meta:
        verbose_name = _("customer")
        verbose_name_plural = _("customers")
        ordering = ["last_name", "second_last_name", "first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "code"],
                condition=~Q(code=""),
                name="customer_code_unique_per_business",
            ),
        ]
        indexes = [
            models.Index(fields=["business", "status"]),
            models.Index(fields=["phone"]),
        ]

    def __str__(self) -> str:
        return self.full_name

    def get_absolute_url(self) -> str:
        return reverse("customers:detail", args=[self.pk])

    @property
    def full_name(self) -> str:
        parts = [self.first_name, self.last_name, self.second_last_name]
        return " ".join(part for part in parts if part).strip()

    @property
    def is_restricted(self) -> bool:
        return self.status == CustomerStatus.RESTRICTED

    def save(self, *args, **kwargs):
        self.national_id = (self.national_id or "").upper().strip()
        self.tax_id = (self.tax_id or "").upper().strip()
        super().save(*args, **kwargs)
        if not self.code:
            self.code = f"CU-{self.pk:05d}"
            super().save(update_fields=["code"])


class PersonalReference(models.Model):
    """Optional contact reference for a customer."""

    customer = models.ForeignKey(
        Customer, verbose_name=_("customer"), on_delete=models.CASCADE,
        related_name="references",
    )
    name = models.CharField(_("name"), max_length=150)
    relationship = models.CharField(_("relationship"), max_length=80, blank=True)
    phone = models.CharField(_("phone"), max_length=20, validators=[validate_phone])
    address = models.CharField(_("address"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("personal reference")
        verbose_name_plural = _("personal references")
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.relationship})" if self.relationship else self.name
