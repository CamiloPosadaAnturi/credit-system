"""Creditos y su calendario de cuotas.

Reglas clave (ver docs/reglas_financieras.md):

* El interes se calcula UNA sola vez, al aprobar el credito, sobre el
  capital inicial. No hay interes compuesto ni recalculo por cada pago.
* La regla de interes del negocio se copia al credito (snapshot), de modo
  que cambiar la tasa del negocio no altera creditos ya aprobados.
* ``saldo_pendiente`` es un campo derivado: siempre se puede reconstruir
  desde las aplicaciones de pago (``apps.pagos.models.AplicacionPago``).
"""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse

from apps.core.dinero import CERO
from apps.core.models import ModeloBase
from apps.core.opciones import FrecuenciaPago, ModalidadInteres, PeriodoTasa


class EstadoCredito(models.TextChoices):
    BORRADOR = "borrador", "Borrador"
    PENDIENTE = "pendiente_aprobacion", "Pendiente de aprobacion"
    APROBADO = "aprobado", "Aprobado"
    DESEMBOLSADO = "desembolsado", "Desembolsado"
    ACTIVO = "activo", "Activo"
    EN_MORA = "en_mora", "En mora"
    LIQUIDADO = "liquidado", "Liquidado"
    CANCELADO = "cancelado", "Cancelado"
    REESTRUCTURADO = "reestructurado", "Reestructurado"


#: Estados en los que el credito tiene saldo exigible y forma parte de la cartera.
ESTADOS_VIGENTES = [
    EstadoCredito.DESEMBOLSADO,
    EstadoCredito.ACTIVO,
    EstadoCredito.EN_MORA,
]
#: Estados en los que el dinero ya salio del negocio.
ESTADOS_DESEMBOLSADOS = ESTADOS_VIGENTES + [
    EstadoCredito.LIQUIDADO,
    EstadoCredito.REESTRUCTURADO,
]
#: Estados anteriores al desembolso: el credito todavia se puede editar.
ESTADOS_EDITABLES = [EstadoCredito.BORRADOR, EstadoCredito.PENDIENTE]


class EstadoCuota(models.TextChoices):
    PENDIENTE = "pendiente", "Pendiente"
    PARCIAL = "parcial", "Parcial"
    PAGADA = "pagada", "Pagada"
    VENCIDA = "vencida", "Vencida"


class CreditoQuerySet(models.QuerySet):
    def vigentes(self):
        return self.filter(estado__in=ESTADOS_VIGENTES)

    def desembolsados(self):
        return self.filter(estado__in=ESTADOS_DESEMBOLSADOS)

    def liquidados(self):
        return self.filter(estado=EstadoCredito.LIQUIDADO)

    def en_mora(self):
        return self.filter(estado=EstadoCredito.EN_MORA)

    def de_negocio(self, negocio):
        return self.filter(negocio=negocio)


class Credito(ModeloBase):
    folio = models.CharField("folio", max_length=30, unique=True, editable=False)
    cliente = models.ForeignKey(
        "clientes.Cliente", verbose_name="cliente", on_delete=models.PROTECT,
        related_name="creditos",
    )
    negocio = models.ForeignKey(
        "negocios.Negocio", verbose_name="negocio", on_delete=models.PROTECT,
        related_name="creditos",
    )
    cobrador = models.ForeignKey(
        "usuarios.Usuario", verbose_name="cobrador asignado", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="creditos_asignados",
        limit_choices_to={"rol": "cobrador"},
    )

    fecha_solicitud = models.DateField("fecha de solicitud")
    fecha_aprobacion = models.DateField("fecha de aprobacion", null=True, blank=True)
    fecha_desembolso = models.DateField("fecha de desembolso", null=True, blank=True)

    capital = models.DecimalField(
        "capital prestado", max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    # --- Snapshot de la regla de interes aplicada -------------------------
    modalidad_interes = models.CharField(
        "modalidad de interes", max_length=20, choices=ModalidadInteres.choices,
        default=ModalidadInteres.FIJO_CAPITAL,
    )
    tasa_interes = models.DecimalField(
        "tasa de interes aplicada", max_digits=7, decimal_places=4,
        default=Decimal("0.4000"),
        help_text="Tanto por uno congelado al aprobar el credito.",
    )
    periodo_tasa = models.CharField(
        "periodo de la tasa", max_length=15, choices=PeriodoTasa.choices,
        default=PeriodoTasa.CONTRATO,
    )

    interes_total = models.DecimalField(
        "interes total", max_digits=12, decimal_places=2, default=CERO)
    total_a_pagar = models.DecimalField(
        "total a pagar", max_digits=12, decimal_places=2, default=CERO)

    frecuencia_pago = models.CharField(
        "frecuencia de pago", max_length=15, choices=FrecuenciaPago.choices,
        default=FrecuenciaPago.SEMANAL,
    )
    dias_personalizados = models.PositiveIntegerField(
        "dias entre cuotas", null=True, blank=True,
        help_text="Solo para frecuencia personalizada.",
    )
    numero_cuotas = models.PositiveIntegerField(
        "numero de cuotas", default=1, validators=[MinValueValidator(1)])
    importe_cuota = models.DecimalField(
        "importe de cada cuota", max_digits=12, decimal_places=2, default=CERO)

    fecha_primer_pago = models.DateField("fecha del primer pago")
    fecha_vencimiento_final = models.DateField(
        "fecha de vencimiento final", null=True, blank=True)

    # --- Saldos derivados (se recalculan desde las aplicaciones de pago) --
    capital_pagado = models.DecimalField(
        "capital pagado", max_digits=12, decimal_places=2, default=CERO)
    interes_pagado = models.DecimalField(
        "interes pagado", max_digits=12, decimal_places=2, default=CERO)
    saldo_pendiente = models.DecimalField(
        "saldo pendiente", max_digits=12, decimal_places=2, default=CERO)

    estado = models.CharField(
        "estado", max_length=25, choices=EstadoCredito.choices,
        default=EstadoCredito.BORRADOR, db_index=True,
    )
    motivo_cancelacion = models.CharField("motivo de cancelacion", max_length=255, blank=True)
    credito_origen = models.ForeignKey(
        "self", verbose_name="credito reestructurado", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="reestructuraciones",
    )
    observaciones = models.TextField("observaciones", blank=True)
    contrato = models.FileField(
        "contrato o documento", upload_to="contratos/%Y/%m/", blank=True, null=True)

    aprobado_por = models.ForeignKey(
        "usuarios.Usuario", verbose_name="aprobado por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="creditos_aprobados",
    )
    desembolsado_por = models.ForeignKey(
        "usuarios.Usuario", verbose_name="desembolsado por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="creditos_desembolsados",
    )

    objects = CreditoQuerySet.as_manager()

    class Meta:
        verbose_name = "credito"
        verbose_name_plural = "creditos"
        ordering = ["-fecha_solicitud", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(capital__gt=0), name="credito_capital_positivo"),
            models.CheckConstraint(
                condition=Q(interes_total__gte=0), name="credito_interes_no_negativo"),
            models.CheckConstraint(
                condition=Q(numero_cuotas__gte=1), name="credito_cuotas_min_1"),
            models.CheckConstraint(
                condition=Q(saldo_pendiente__gte=0), name="credito_saldo_no_negativo"),
        ]
        indexes = [
            models.Index(fields=["negocio", "estado"]),
            models.Index(fields=["cliente", "estado"]),
            models.Index(fields=["cobrador", "estado"]),
        ]

    def __str__(self) -> str:
        return f"{self.folio} - {self.cliente}"

    def get_absolute_url(self) -> str:
        return reverse("creditos:detalle", args=[self.pk])

    # --- Propiedades de solo lectura -------------------------------------
    @property
    def total_pagado(self) -> Decimal:
        return self.capital_pagado + self.interes_pagado

    @property
    def esta_vigente(self) -> bool:
        return self.estado in ESTADOS_VIGENTES

    @property
    def es_editable(self) -> bool:
        """Un credito desembolsado no se edita: se ajusta con operaciones auditadas."""
        return self.estado in ESTADOS_EDITABLES

    @property
    def porcentaje_pagado(self) -> Decimal:
        if not self.total_a_pagar:
            return CERO
        return (self.total_pagado * 100 / self.total_a_pagar).quantize(Decimal("0.01"))

    @property
    def interes_por_mil(self) -> Decimal:
        return (self.tasa_interes * 1000).quantize(Decimal("0.01"))

    def cuotas_vencidas(self):
        from apps.core.fechas import hoy_local

        return self.cuotas.filter(
            fecha_vencimiento__lt=hoy_local()
        ).exclude(estado=EstadoCuota.PAGADA)

    @property
    def saldo_vencido(self) -> Decimal:
        total = CERO
        for cuota in self.cuotas_vencidas():
            total += cuota.saldo
        return total

    @property
    def dias_atraso(self) -> int:
        """Dias de atraso del credito = los de su cuota vencida mas antigua."""
        cuota = self.cuotas_vencidas().order_by("fecha_vencimiento").first()
        return cuota.dias_atraso if cuota else 0

    @property
    def proxima_cuota(self):
        return (
            self.cuotas.exclude(estado=EstadoCuota.PAGADA)
            .order_by("fecha_vencimiento")
            .first()
        )


class Cuota(models.Model):
    """Una linea del calendario de pagos del credito."""

    credito = models.ForeignKey(
        Credito, verbose_name="credito", on_delete=models.CASCADE, related_name="cuotas")
    numero = models.PositiveIntegerField("numero de cuota")
    fecha_vencimiento = models.DateField("fecha de vencimiento", db_index=True)
    importe_programado = models.DecimalField(
        "importe programado", max_digits=12, decimal_places=2)
    capital_programado = models.DecimalField(
        "capital programado", max_digits=12, decimal_places=2, default=CERO)
    interes_programado = models.DecimalField(
        "interes programado", max_digits=12, decimal_places=2, default=CERO)
    importe_pagado = models.DecimalField(
        "importe pagado", max_digits=12, decimal_places=2, default=CERO)
    capital_pagado = models.DecimalField(
        "capital pagado", max_digits=12, decimal_places=2, default=CERO)
    interes_pagado = models.DecimalField(
        "interes pagado", max_digits=12, decimal_places=2, default=CERO)
    estado = models.CharField(
        "estado", max_length=12, choices=EstadoCuota.choices,
        default=EstadoCuota.PENDIENTE, db_index=True)
    fecha_liquidacion = models.DateField("fecha de liquidacion", null=True, blank=True)

    class Meta:
        verbose_name = "cuota"
        verbose_name_plural = "cuotas"
        ordering = ["credito", "numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["credito", "numero"], name="cuota_numero_unico_por_credito"),
            models.CheckConstraint(
                condition=Q(importe_programado__gte=0), name="cuota_importe_no_negativo"),
        ]

    def __str__(self) -> str:
        return f"Cuota {self.numero}/{self.credito.numero_cuotas} de {self.credito.folio}"

    @property
    def saldo(self) -> Decimal:
        return self.importe_programado - self.importe_pagado

    @property
    def saldo_capital(self) -> Decimal:
        return self.capital_programado - self.capital_pagado

    @property
    def saldo_interes(self) -> Decimal:
        return self.interes_programado - self.interes_pagado

    @property
    def esta_pagada(self) -> bool:
        return self.saldo <= CERO

    @property
    def dias_atraso(self) -> int:
        from apps.core.fechas import hoy_local

        if self.esta_pagada:
            return 0
        dias = (hoy_local() - self.fecha_vencimiento).days
        return max(dias, 0)

    def dias_atraso_con_gracia(self, dias_gracia: int = 0) -> int:
        return max(self.dias_atraso - dias_gracia, 0)
