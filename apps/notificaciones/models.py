"""Avisos internos del sistema (no envia SMS ni correos al cliente)."""
from django.db import models


class TipoNotificacion(models.TextChoices):
    INFORMATIVA = "info", "Informativa"
    ALERTA = "alerta", "Alerta"
    MORA = "mora", "Mora"


class Notificacion(models.Model):
    negocio = models.ForeignKey(
        "negocios.Negocio", verbose_name="negocio", on_delete=models.CASCADE,
        related_name="notificaciones")
    usuario = models.ForeignKey(
        "usuarios.Usuario", verbose_name="dirigida a", on_delete=models.CASCADE,
        null=True, blank=True, related_name="notificaciones",
        help_text="Si esta vacia, la ven todos los usuarios del negocio.")
    tipo = models.CharField(
        "tipo", max_length=10, choices=TipoNotificacion.choices,
        default=TipoNotificacion.INFORMATIVA)
    titulo = models.CharField("titulo", max_length=150)
    mensaje = models.TextField("mensaje", blank=True)
    url = models.CharField("enlace", max_length=255, blank=True)
    leida = models.BooleanField("leida", default=False)
    creado_en = models.DateTimeField("creado en", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "notificacion"
        verbose_name_plural = "notificaciones"
        ordering = ["-creado_en"]

    def __str__(self) -> str:
        return self.titulo
