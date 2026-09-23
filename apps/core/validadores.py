"""Validadores de identificadores mexicanos y de importes."""
import re

from django.core.exceptions import ValidationError

RFC_REGEX = re.compile(
    r"^([A-ZÑ&]{3,4})\d{6}([A-Z\d]{3})$", re.IGNORECASE
)
CURP_REGEX = re.compile(
    r"^[A-Z][AEIOUX][A-Z]{2}\d{6}[HM][A-Z]{2}[B-DF-HJ-NP-TV-Z]{3}[A-Z\d]\d$",
    re.IGNORECASE,
)
CP_REGEX = re.compile(r"^\d{5}$")
TELEFONO_REGEX = re.compile(r"^[\d\s\-\+\(\)]{7,20}$")


def validar_rfc(valor: str) -> None:
    if not valor:
        return
    if not RFC_REGEX.match(valor.strip()):
        raise ValidationError(
            "El RFC no tiene un formato valido (12 caracteres para persona moral, "
            "13 para persona fisica)."
        )


def validar_curp(valor: str) -> None:
    if not valor:
        return
    if not CURP_REGEX.match(valor.strip()):
        raise ValidationError("La CURP no tiene un formato valido (18 caracteres).")


def validar_codigo_postal(valor: str) -> None:
    if not valor:
        return
    if not CP_REGEX.match(valor.strip()):
        raise ValidationError("El codigo postal debe tener 5 digitos.")


def validar_telefono(valor: str) -> None:
    if not valor:
        return
    if not TELEFONO_REGEX.match(valor.strip()):
        raise ValidationError("El telefono no tiene un formato valido.")


def validar_importe_positivo(valor) -> None:
    if valor is None:
        return
    if valor <= 0:
        raise ValidationError("El importe debe ser mayor que cero.")
