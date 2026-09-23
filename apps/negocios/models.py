"""Negocios / sucursales y su configuracion comercial."""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse

from apps.core.estados_mx import ESTADOS_MX
from apps.core.models import ModeloBase
from apps.core.opciones import FrecuenciaPago, ModalidadInteres, PeriodoTasa
from apps.core.validadores import validar_rfc, validar_telefono


class NegocioQuerySet(models.QuerySet):
    def activos(self):
        return self.filter(activo=True)


class Negocio(ModeloBase):
    """Un negocio o sucursal que otorga creditos.

    Cada negocio aisla su informacion: clientes, creditos, pagos y cartera
    pertenecen siempre a un negocio y nunca se mezclan entre si.
    """

    nombre_comercial = models.CharField("nombre comercial", max_length=150)
    razon_social = models.CharField("razon social", max_length=200, blank=True)
    rfc = models.CharField("RFC", max_length=13, blank=True, validators=[validar_rfc])
    telefono = models.CharField("telefono", max_length=20, blank=True,
                                validators=[validar_telefono])
    email = models.EmailField("correo electronico", blank=True)
    direccion = models.CharField("direccion", max_length=255, blank=True)
    ciudad = models.CharField("ciudad", max_length=100, blank=True)
    estado = models.CharField("estado", max_length=5, choices=ESTADOS_MX, blank=True)
    responsable = models.ForeignKey(
        "usuarios.Usuario",
        verbose_name="responsable",
        on_delete=models.PROTECT,
        related_name="negocios_a_cargo",
        null=True,
        blank=True,
    )
    activo = models.BooleanField("activo", default=True)

    # --- Configuracion de intereses predeterminada ------------------------
    modalidad_interes = models.CharField(
        "modalidad de interes",
        max_length=20,
        choices=ModalidadInteres.choices,
        default=ModalidadInteres.FIJO_CAPITAL,
    )
    tasa_interes = models.DecimalField(
        "tasa de interes",
        max_digits=7,
        decimal_places=4,
        default=Decimal("0.4000"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Expresada en tanto por uno. 0.4000 = 40% (400 MXN por cada 1,000 MXN).",
    )
    periodo_tasa = models.CharField(
        "periodo de la tasa",
        max_length=15,
        choices=PeriodoTasa.choices,
        default=PeriodoTasa.CONTRATO,
        help_text="Periodo contractual al que corresponde la tasa. Debe coincidir "
                  "con lo pactado en el contrato.",
    )
    frecuencia_pago = models.CharField(
        "frecuencia de pago predeterminada",
        max_length=15,
        choices=FrecuenciaPago.choices,
        default=FrecuenciaPago.SEMANAL,
    )
    numero_cuotas = models.PositiveIntegerField(
        "numero de cuotas predeterminado", default=4,
        validators=[MinValueValidator(1)],
    )

    # --- Configuracion de mora -------------------------------------------
    dias_gracia = models.PositiveIntegerField(
        "dias de gracia", default=0,
        help_text="Dias posteriores al vencimiento antes de considerar la cuota vencida.",
    )
    aplica_mora = models.BooleanField(
        "aplica cargo moratorio", default=False,
        help_text="Si esta desactivado, el sistema NO genera cargos por atraso. "
                  "Actívalo solo con una politica documentada y autorizada.",
    )
    tasa_mora = models.DecimalField(
        "tasa moratoria diaria", max_digits=7, decimal_places=4, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Tanto por uno sobre el saldo vencido, por dia de atraso.",
    )
    permite_liquidacion_anticipada = models.BooleanField(
        "permite liquidacion anticipada", default=True,
    )
    descuento_liquidacion_anticipada = models.DecimalField(
        "descuento por liquidacion anticipada", max_digits=7, decimal_places=4,
        default=Decimal("0"),
        help_text="Tanto por uno de descuento sobre el interes NO devengado. "
                  "0 = se cobra el total contractual.",
    )

    observaciones = models.TextField("observaciones", blank=True)

    objects = NegocioQuerySet.as_manager()

    class Meta:
        verbose_name = "negocio"
        verbose_name_plural = "negocios"
        ordering = ["nombre_comercial"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(tasa_interes__gte=0), name="negocio_tasa_no_negativa"
            ),
            models.CheckConstraint(
                condition=models.Q(numero_cuotas__gte=1), name="negocio_cuotas_min_1"
            ),
        ]

    def __str__(self) -> str:
        return self.nombre_comercial

    def get_absolute_url(self) -> str:
        return reverse("negocios:detalle", args=[self.pk])

    @property
    def tasa_porcentaje(self) -> Decimal:
        return (self.tasa_interes * 100).quantize(Decimal("0.01"))

    @property
    def interes_por_mil(self) -> Decimal:
        """Cuanto interes se cobra por cada 1,000 MXN prestados."""
        return (self.tasa_interes * 1000).quantize(Decimal("0.01"))

    def regla_interes_actual(self) -> dict:
        """Copia de la regla vigente, para congelarla en cada credito."""
        return {
            "modalidad_interes": self.modalidad_interes,
            "tasa_interes": self.tasa_interes,
            "periodo_tasa": self.periodo_tasa,
        }
