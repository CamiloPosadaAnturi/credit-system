from django.contrib import admin

from apps.auditoria.models import RegistroAuditoria


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("fecha", "usuario", "accion", "modelo", "objeto_id", "descripcion")
    list_filter = ("accion", "modelo", "negocio")
    search_fields = ("descripcion", "objeto_id", "usuario__username")
    date_hierarchy = "fecha"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
