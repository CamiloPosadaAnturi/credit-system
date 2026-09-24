"""Custom user model with the business roles."""
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.utils.translation import gettext_lazy as _


class Role(models.TextChoices):
    SUPERADMIN = "superadmin", _("Super administrator")
    ADMIN = "admin", _("Business administrator")
    MANAGER = "manager", _("Manager or supervisor")
    COLLECTOR = "collector", _("Collector")
    VIEWER = "viewer", _("Read-only user")


class UserQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def collectors(self):
        return self.filter(role=Role.COLLECTOR, is_active=True)

    def of_business(self, business):
        return self.filter(businesses=business)


class UserManagerWithQuerySet(UserManager.from_queryset(UserQuerySet)):
    """Keeps Django's create_user/create_superuser on the custom queryset."""


class User(AbstractUser):
    """A system user.

    Access is controlled along two axes:

    * ``role``: which actions the user may run.
    * ``businesses``: which businesses or branches the user may operate on.

    The super administrator needs no memberships: they see the whole platform.
    """

    role = models.CharField(_("role"), max_length=20, choices=Role.choices,
                            default=Role.VIEWER)
    phone = models.CharField(_("phone"), max_length=20, blank=True)
    businesses = models.ManyToManyField(
        "businesses.Business",
        verbose_name=_("authorized businesses"),
        related_name="users",
        blank=True,
        help_text=_("Businesses or branches this user may operate on."),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    objects = UserManagerWithQuerySet()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["first_name", "last_name", "username"]

    def __str__(self) -> str:
        return self.full_name or self.username

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_superadmin(self) -> bool:
        return self.role == Role.SUPERADMIN or self.is_superuser

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

    @property
    def is_manager(self) -> bool:
        return self.role == Role.MANAGER

    @property
    def is_collector(self) -> bool:
        return self.role == Role.COLLECTOR

    @property
    def is_viewer(self) -> bool:
        return self.role == Role.VIEWER

    def can(self, action: str) -> bool:
        """Shortcut into the permission matrix (``apps.users.permissions``)."""
        from apps.users.permissions import can

        return can(self, action)

    def allowed_businesses(self):
        from apps.users.permissions import allowed_businesses

        return allowed_businesses(self)
