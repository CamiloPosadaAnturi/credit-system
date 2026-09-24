"""Validators for Mexican identifiers and for monetary amounts."""
import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

TAX_ID_REGEX = re.compile(r"^([A-ZN&]{3,4})\d{6}([A-Z\d]{3})$", re.IGNORECASE)
NATIONAL_ID_REGEX = re.compile(
    r"^[A-Z][AEIOUX][A-Z]{2}\d{6}[HM][A-Z]{2}[B-DF-HJ-NP-TV-Z]{3}[A-Z\d]\d$",
    re.IGNORECASE,
)
POSTAL_CODE_REGEX = re.compile(r"^\d{5}$")
PHONE_REGEX = re.compile(r"^[\d\s\-\+\(\)]{7,20}$")


def validate_tax_id(value: str) -> None:
    """Validate a Mexican RFC (12 characters for companies, 13 for individuals)."""
    if not value:
        return
    if not TAX_ID_REGEX.match(value.strip()):
        raise ValidationError(
            _("The RFC format is not valid (12 characters for a company, "
              "13 for an individual).")
        )


def validate_national_id(value: str) -> None:
    """Validate a Mexican CURP (18 characters)."""
    if not value:
        return
    if not NATIONAL_ID_REGEX.match(value.strip()):
        raise ValidationError(_("The CURP format is not valid (18 characters)."))


def validate_postal_code(value: str) -> None:
    if not value:
        return
    if not POSTAL_CODE_REGEX.match(value.strip()):
        raise ValidationError(_("The postal code must have 5 digits."))


def validate_phone(value: str) -> None:
    if not value:
        return
    if not PHONE_REGEX.match(value.strip()):
        raise ValidationError(_("The phone number format is not valid."))


def validate_positive_amount(value) -> None:
    if value is None:
        return
    if value <= 0:
        raise ValidationError(_("The amount must be greater than zero."))
