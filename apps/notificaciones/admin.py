from django.contrib import admin

from apps.notificaciones.models import Notificacion


@admin.register(Notificacion)
class NotificacionAdmin(admin.ModelAdmin):
    list_display = ("titulo", "negocio", "usuario", "tipo", "leida", "creado_en")
    list_filter = ("tipo", "leida", "negocio")
