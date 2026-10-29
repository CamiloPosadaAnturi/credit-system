"""Customers of a business."""
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.core.validators import validate_phone


class CustomerQuerySet(models.QuerySet):
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
        )


class Customer(BaseModel):
    """A person who receives loans from a business.

    Data protection: only the data the operation needs is stored (name and
    phone, plus internal notes).
    """

    business = models.ForeignKey(
        "businesses.Business", verbose_name=_("business"), on_delete=models.PROTECT,
        related_name="customers",
    )
    first_name = models.CharField(_("first name(s)"), max_length=100)
    last_name = models.CharField(_("last name"), max_length=80)
    second_last_name = models.CharField(_("second last name"), max_length=80, blank=True)

    phone = models.CharField(_("primary phone"), max_length=20,
                             validators=[validate_phone])

    notes = models.TextField(_("internal notes"), blank=True)

    objects = CustomerQuerySet.as_manager()

    class Meta:
        verbose_name = _("customer")
        verbose_name_plural = _("customers")
        ordering = ["last_name", "second_last_name", "first_name"]
        indexes = [
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
