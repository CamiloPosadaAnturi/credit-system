"""Modelo de usuario personalizado con roles del negocio."""
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class Rol(models.TextChoices):
    SUPERADMIN = "superadmin", "Superadministrador"
    ADMIN = "admin", "Administrador del negocio"
    GERENTE = "gerente", "Gerente o supervisor"
    COBRADOR = "cobrador", "Cobrador"
    CONSULTA = "consulta", "Usuario de consulta"


class UsuarioQuerySet(models.QuerySet):
    def activos(self):
        return self.filter(is_active=True)

    def cobradores(self):
        return self.filter(rol=Rol.COBRADOR, is_active=True)

    def de_negocio(self, negocio):
        return self.filter(negocios=negocio)


class UsuarioManager(UserManager.from_queryset(UsuarioQuerySet)):
    """Manager del usuario: conserva create_user/create_superuser de Django."""


class Usuario(AbstractUser):
    """Usuario del sistema.

    El acceso a la informacion se controla por dos ejes:

    * ``rol``: que acciones puede ejecutar.
    * ``negocios``: sobre que negocios o sucursales puede operar.

    El superadministrador no necesita membresias: ve toda la plataforma.
    """

    rol = models.CharField("rol", max_length=20, choices=Rol.choices, default=Rol.CONSULTA)
    telefono = models.CharField("telefono", max_length=20, blank=True)
    negocios = models.ManyToManyField(
        "negocios.Negocio",
        verbose_name="negocios autorizados",
        related_name="usuarios",
        blank=True,
        help_text="Negocios o sucursales sobre los que este usuario puede operar.",
    )
    creado_en = models.DateTimeField("creado en", auto_now_add=True)

    objects = UsuarioManager()

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["first_name", "last_name", "username"]

    def __str__(self) -> str:
        return self.nombre_completo or self.username

    @property
    def nombre_completo(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def es_superadmin(self) -> bool:
        return self.rol == Rol.SUPERADMIN or self.is_superuser

    @property
    def es_admin(self) -> bool:
        return self.rol == Rol.ADMIN

    @property
    def es_gerente(self) -> bool:
        return self.rol == Rol.GERENTE

    @property
    def es_cobrador(self) -> bool:
        return self.rol == Rol.COBRADOR

    @property
    def es_consulta(self) -> bool:
        return self.rol == Rol.CONSULTA

    def puede(self, accion: str) -> bool:
        """Atajo hacia la matriz de permisos (``apps.usuarios.permisos``)."""
        from apps.usuarios.permisos import puede

        return puede(self, accion)

    def negocios_permitidos(self):
        from apps.usuarios.permisos import negocios_permitidos

        return negocios_permitidos(self)
