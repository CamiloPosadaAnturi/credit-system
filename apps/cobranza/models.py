"""Gestiones de cobranza: el registro del trabajo diario del cobrador."""
from django.db import models

from apps.core.dinero import CERO


class TipoGestion(models.TextChoices):
    LLAMADA = "llamada", "Llamada realizada"
    MENSAJE = "mensaje", "Mensaje enviado"
    VISITA = "visita", "Visita realizada"
    PROMESA = "promesa", "Promesa de pago"
    NO_LOCALIZADO = "no_localizado", "Cliente no localizado"
    ACUERDO = "acuerdo", "Acuerdo de pago"


class ResultadoGestion(models.TextChoices):
    PAGO_INMEDIATO = "pago", "Pago realizado"
    PROMESA = "promesa", "Promete pagar"
    SIN_RESPUESTA = "sin_respuesta", "Sin respuesta"
    NEGATIVA = "negativa", "Se niega a pagar"
    REAGENDA = "reagenda", "Reagendar contacto"
    OTRO = "otro", "Otro"


class GestionCobranza(models.Model):
    credito = models.ForeignKey(
        "creditos.Credito", verbose_name="credito", on_delete=models.CASCADE,
        related_name="gestiones")
    cliente = models.ForeignKey(
        "clientes.Cliente", verbose_name="cliente", on_delete=models.CASCADE,
        related_name="gestiones")
    negocio = models.ForeignKey(
        "negocios.Negocio", verbose_name="negocio", on_delete=models.CASCADE,
        related_name="gestiones")
    usuario = models.ForeignKey(
        "usuarios.Usuario", verbose_name="gestionado por", on_delete=models.PROTECT,
        related_name="gestiones")

    fecha = models.DateTimeField("fecha de la gestion", db_index=True)
    tipo = models.CharField("tipo de gestion", max_length=20, choices=TipoGestion.choices)
    resultado = models.CharField(
        "resultado", max_length=20, choices=ResultadoGestion.choices,
        default=ResultadoGestion.OTRO)

    monto_prometido = models.DecimalField(
        "monto prometido", max_digits=12, decimal_places=2, default=CERO)
    fecha_promesa = models.DateField("fecha de la promesa", null=True, blank=True)
    proxima_fecha_contacto = models.DateField(
        "proxima fecha de contacto", null=True, blank=True, db_index=True)
    observaciones = models.TextField("observaciones", blank=True)
    creado_en = models.DateTimeField("creado en", auto_now_add=True)

    class Meta:
        verbose_name = "gestion de cobranza"
        verbose_name_plural = "gestiones de cobranza"
        ordering = ["-fecha"]
        indexes = [
            models.Index(fields=["negocio", "-fecha"]),
            models.Index(fields=["usuario", "-fecha"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} - {self.cliente} ({self.fecha:%d/%m/%Y})"

    @property
    def promesa_cumplida(self) -> bool:
        """La promesa se considera cumplida si hubo pagos desde la gestion."""
        if not self.fecha_promesa or self.monto_prometido <= CERO:
            return False
        from django.db.models import Sum

        from apps.pagos.models import EstadoPago, Pago

        pagado = Pago.objects.filter(
            credito=self.credito, estado=EstadoPago.CONFIRMADO,
            fecha__gte=self.fecha,
        ).aggregate(total=Sum("importe"))["total"] or CERO
        return pagado >= self.monto_prometido
