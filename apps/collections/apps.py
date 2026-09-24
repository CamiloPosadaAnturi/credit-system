from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CollectionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.collections"
    verbose_name = _("Collections")
