"""Clientes del negocio y sus referencias personales."""
from django.db import models
from django.db.models import Q
from django.urls import reverse

from apps.core.estados_mx import ESTADOS_MX
from apps.core.models import ModeloBase
from apps.core.validadores import (
    validar_codigo_postal,
    validar_curp,
    validar_rfc,
    validar_telefono,
)


class EstadoCliente(models.TextChoices):
    ACTIVO = "activo", "Activo"
    INACTIVO = "inactivo", "Inactivo"
    RESTRINGIDO = "restringido", "Restringido"


class ClienteQuerySet(models.QuerySet):
    def activos(self):
        return self.filter(estado=EstadoCliente.ACTIVO)

    def de_negocio(self, negocio):
        return self.filter(negocio=negocio)

    def buscar(self, termino: str):
        if not termino:
            return self
        return self.filter(
            Q(nombres__icontains=termino)
            | Q(apellido_paterno__icontains=termino)
            | Q(apellido_materno__icontains=termino)
            | Q(telefono_principal__icontains=termino)
            | Q(codigo__icontains=termino)
        )


class Cliente(ModeloBase):
    """Persona que recibe creditos de un negocio.

    Proteccion de datos: CURP y RFC son opcionales y solo se muestran a
    los roles con el permiso ``ver_datos_sensibles``. No se almacena mas
    informacion personal de la estrictamente necesaria para la operacion.
    """

    negocio = models.ForeignKey(
        "negocios.Negocio", verbose_name="negocio", on_delete=models.PROTECT,
        related_name="clientes",
    )
    codigo = models.CharField(
        "codigo", max_length=20, blank=True,
        help_text="Identificador interno del cliente dentro del negocio.",
    )
    nombres = models.CharField("nombre(s)", max_length=100)
    apellido_paterno = models.CharField("apellido paterno", max_length=80)
    apellido_materno = models.CharField("apellido materno", max_length=80, blank=True)

    curp = models.CharField("CURP", max_length=18, blank=True, validators=[validar_curp])
    rfc = models.CharField("RFC", max_length=13, blank=True, validators=[validar_rfc])
    fecha_nacimiento = models.DateField("fecha de nacimiento", null=True, blank=True)

    telefono_principal = models.CharField(
        "telefono principal", max_length=20, validators=[validar_telefono])
    telefono_alterno = models.CharField(
        "telefono alterno", max_length=20, blank=True, validators=[validar_telefono])
    email = models.EmailField("correo electronico", blank=True)

    direccion = models.CharField("direccion", max_length=255, blank=True)
    ciudad = models.CharField("ciudad", max_length=100, blank=True)
    estado_republica = models.CharField(
        "estado", max_length=5, choices=ESTADOS_MX, blank=True)
    codigo_postal = models.CharField(
        "codigo postal", max_length=5, blank=True, validators=[validar_codigo_postal])

    ocupacion = models.CharField("ocupacion o actividad economica", max_length=120, blank=True)

    cobrador = models.ForeignKey(
        "usuarios.Usuario", verbose_name="cobrador asignado", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="clientes_asignados",
        limit_choices_to={"rol": "cobrador"},
    )
    estado = models.CharField(
        "estado", max_length=15, choices=EstadoCliente.choices,
        default=EstadoCliente.ACTIVO)
    observaciones = models.TextField("observaciones internas", blank=True)

    objects = ClienteQuerySet.as_manager()

    class Meta:
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        ordering = ["apellido_paterno", "apellido_materno", "nombres"]
        constraints = [
            models.UniqueConstraint(
                fields=["negocio", "codigo"],
                condition=~Q(codigo=""),
                name="cliente_codigo_unico_por_negocio",
            ),
        ]
        indexes = [
            models.Index(fields=["negocio", "estado"]),
            models.Index(fields=["telefono_principal"]),
        ]

    def __str__(self) -> str:
        return self.nombre_completo

    def get_absolute_url(self) -> str:
        return reverse("clientes:detalle", args=[self.pk])

    @property
    def nombre_completo(self) -> str:
        partes = [self.nombres, self.apellido_paterno, self.apellido_materno]
        return " ".join(p for p in partes if p).strip()

    @property
    def esta_restringido(self) -> bool:
        return self.estado == EstadoCliente.RESTRINGIDO

    def save(self, *args, **kwargs):
        self.curp = (self.curp or "").upper().strip()
        self.rfc = (self.rfc or "").upper().strip()
        super().save(*args, **kwargs)
        if not self.codigo:
            self.codigo = f"CL-{self.pk:05d}"
            super().save(update_fields=["codigo"])


class ReferenciaPersonal(models.Model):
    """Referencia de contacto del cliente (opcional)."""

    cliente = models.ForeignKey(
        Cliente, verbose_name="cliente", on_delete=models.CASCADE,
        related_name="referencias",
    )
    nombre = models.CharField("nombre", max_length=150)
    parentesco = models.CharField("parentesco o relacion", max_length=80, blank=True)
    telefono = models.CharField("telefono", max_length=20, validators=[validar_telefono])
    direccion = models.CharField("direccion", max_length=255, blank=True)

    class Meta:
        verbose_name = "referencia personal"
        verbose_name_plural = "referencias personales"
        ordering = ["nombre"]

    def __str__(self) -> str:
        return f"{self.nombre} ({self.parentesco})" if self.parentesco else self.nombre
