"""Pagos, condonaciones y su aplicacion a las cuotas.

Diseno:

* ``Pago`` es el hecho economico: el dinero que entrego el cliente.
* ``AplicacionPago`` es el detalle de COMO se repartio ese dinero entre
  cuotas, separando capital e interes. Es la fuente de verdad para
  reconstruir el saldo del credito en cualquier momento.
* Un pago confirmado NUNCA se borra ni se edita: se reversa, y el reverso
  queda registrado con su motivo y su autor.
"""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.core.dinero import CERO


class MetodoPago(models.TextChoices):
    EFECTIVO = "efectivo", "Efectivo"
    TRANSFERENCIA = "transferencia", "Transferencia"
    DEPOSITO = "deposito", "Deposito"
    OTRO = "otro", "Otro"


class EstadoPago(models.TextChoices):
    CONFIRMADO = "confirmado", "Confirmado"
    REVERSADO = "reversado", "Reversado"


class TipoPago(models.TextChoices):
    PAGO = "pago", "Pago del cliente"
    CONDONACION = "condonacion", "Condonacion / descuento autorizado"


class PagoQuerySet(models.QuerySet):
    def confirmados(self):
        return self.filter(estado=EstadoPago.CONFIRMADO)

    def en_efectivo_real(self):
        """Solo dinero efectivamente recibido (excluye condonaciones)."""
        return self.confirmados().filter(tipo=TipoPago.PAGO)

    def del_dia(self, fecha):
        return self.filter(fecha__date=fecha)


class Pago(models.Model):
    folio = models.CharField("folio", max_length=30, unique=True, editable=False)
    credito = models.ForeignKey(
        "creditos.Credito", verbose_name="credito", on_delete=models.PROTECT,
        related_name="pagos")
    cliente = models.ForeignKey(
        "clientes.Cliente", verbose_name="cliente", on_delete=models.PROTECT,
        related_name="pagos")
    negocio = models.ForeignKey(
        "negocios.Negocio", verbose_name="negocio", on_delete=models.PROTECT,
        related_name="pagos")

    fecha = models.DateTimeField("fecha y hora del pago", db_index=True)
    importe = models.DecimalField(
        "importe recibido", max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))])
    importe_aplicado = models.DecimalField(
        "importe aplicado a cuotas", max_digits=12, decimal_places=2, default=CERO)
    excedente = models.DecimalField(
        "excedente no aplicado", max_digits=12, decimal_places=2, default=CERO,
        help_text="Solo se permite con autorizacion explicita al registrar el pago.")

    metodo = models.CharField(
        "metodo de pago", max_length=15, choices=MetodoPago.choices,
        default=MetodoPago.EFECTIVO)
    tipo = models.CharField(
        "tipo", max_length=15, choices=TipoPago.choices, default=TipoPago.PAGO)
    estado = models.CharField(
        "estado", max_length=12, choices=EstadoPago.choices,
        default=EstadoPago.CONFIRMADO, db_index=True)

    recibido_por = models.ForeignKey(
        "usuarios.Usuario", verbose_name="registrado por", on_delete=models.PROTECT,
        related_name="pagos_recibidos")
    cobrador = models.ForeignKey(
        "usuarios.Usuario", verbose_name="cobrador", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="pagos_gestionados")

    referencia = models.CharField("referencia de la transaccion", max_length=80, blank=True)
    observaciones = models.TextField("observaciones", blank=True)

    clave_idempotencia = models.CharField(
        "clave de idempotencia", max_length=64, blank=True,
        help_text="Evita que un mismo formulario registre el pago dos veces.")

    # --- Reverso ----------------------------------------------------------
    motivo_reverso = models.CharField("motivo del reverso", max_length=255, blank=True)
    reversado_por = models.ForeignKey(
        "usuarios.Usuario", verbose_name="reversado por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="pagos_reversados")
    reversado_en = models.DateTimeField("fecha del reverso", null=True, blank=True)

    creado_en = models.DateTimeField("creado en", auto_now_add=True)

    objects = PagoQuerySet.as_manager()

    class Meta:
        verbose_name = "pago"
        verbose_name_plural = "pagos"
        ordering = ["-fecha", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(importe__gt=0), name="pago_importe_positivo"),
            models.CheckConstraint(
                condition=Q(excedente__gte=0), name="pago_excedente_no_negativo"),
            models.UniqueConstraint(
                fields=["clave_idempotencia"],
                condition=~Q(clave_idempotencia=""),
                name="pago_clave_idempotencia_unica"),
        ]
        indexes = [
            models.Index(fields=["negocio", "estado", "-fecha"]),
            models.Index(fields=["credito", "estado"]),
        ]

    def __str__(self) -> str:
        return f"{self.folio} - {self.importe} MXN"

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("pagos:detalle", args=[self.pk])

    @property
    def esta_confirmado(self) -> bool:
        return self.estado == EstadoPago.CONFIRMADO

    @property
    def es_condonacion(self) -> bool:
        return self.tipo == TipoPago.CONDONACION


class AplicacionPago(models.Model):
    """Distribucion de un pago sobre una cuota concreta.

    Guardar esta distribucion permite reconstruir el saldo del credito
    linea por linea, sin depender de acumulados.
    """

    pago = models.ForeignKey(
        Pago, verbose_name="pago", on_delete=models.CASCADE, related_name="aplicaciones")
    cuota = models.ForeignKey(
        "creditos.Cuota", verbose_name="cuota", on_delete=models.PROTECT,
        related_name="aplicaciones")
    importe = models.DecimalField("importe aplicado", max_digits=12, decimal_places=2)
    capital = models.DecimalField("capital", max_digits=12, decimal_places=2, default=CERO)
    interes = models.DecimalField("interes", max_digits=12, decimal_places=2, default=CERO)
    creado_en = models.DateTimeField("creado en", auto_now_add=True)

    class Meta:
        verbose_name = "aplicacion de pago"
        verbose_name_plural = "aplicaciones de pago"
        ordering = ["pago", "cuota__numero"]
        constraints = [
            models.CheckConstraint(
                condition=Q(importe__gt=0), name="aplicacion_importe_positivo"),
        ]

    def __str__(self) -> str:
        return f"{self.pago.folio} -> cuota {self.cuota.numero}: {self.importe}"
