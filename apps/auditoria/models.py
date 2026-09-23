"""Bitacora de operaciones criticas.

Los registros de auditoria son inmutables: se agregan, nunca se editan
ni se borran desde la aplicacion.
"""
from django.db import models


class TipoAccion(models.TextChoices):
    CREAR = "crear", "Creacion"
    EDITAR = "editar", "Edicion"
    DESACTIVAR = "desactivar", "Desactivacion"
    APROBAR = "aprobar", "Aprobacion"
    DESEMBOLSAR = "desembolsar", "Desembolso"
    CANCELAR = "cancelar", "Cancelacion"
    REESTRUCTURAR = "reestructurar", "Reestructuracion"
    PAGO = "pago", "Registro de pago"
    REVERSO = "reverso", "Reverso de pago"
    GESTION = "gestion", "Gestion de cobranza"
    ACCESO = "acceso", "Acceso al sistema"
    EXPORTAR = "exportar", "Exportacion de datos"


class RegistroAuditoria(models.Model):
    fecha = models.DateTimeField("fecha", auto_now_add=True, db_index=True)
    usuario = models.ForeignKey(
        "usuarios.Usuario", verbose_name="usuario", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="registros_auditoria",
    )
    negocio = models.ForeignKey(
        "negocios.Negocio", verbose_name="negocio", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="registros_auditoria",
    )
    accion = models.CharField("accion", max_length=20, choices=TipoAccion.choices)
    modelo = models.CharField("modelo", max_length=60, blank=True)
    objeto_id = models.CharField("id del objeto", max_length=40, blank=True)
    descripcion = models.CharField("descripcion", max_length=255)
    datos = models.JSONField("datos", default=dict, blank=True)
    ip = models.GenericIPAddressField("IP", null=True, blank=True)

    class Meta:
        verbose_name = "registro de auditoria"
        verbose_name_plural = "registros de auditoria"
        ordering = ["-fecha"]
        indexes = [
            models.Index(fields=["modelo", "objeto_id"]),
            models.Index(fields=["accion", "-fecha"]),
        ]

    def __str__(self) -> str:
        return f"{self.fecha:%Y-%m-%d %H:%M} {self.get_accion_display()} - {self.descripcion}"
