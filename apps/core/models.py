"""Modelos abstractos compartidos por todas las apps del sistema."""
from django.conf import settings
from django.db import models


class ModeloBase(models.Model):
    """Marca de tiempo y trazabilidad basica de creacion/modificacion."""

    creado_en = models.DateTimeField("creado en", auto_now_add=True, db_index=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="creado por",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="actualizado por",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        abstract = True
