from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class BusinessesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.businesses"
    verbose_name = _("Businesses and branches")
