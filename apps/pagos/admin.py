from django.contrib import admin

from apps.pagos.models import AplicacionPago, Pago


class AplicacionInline(admin.TabularInline):
    model = AplicacionPago
    extra = 0
    readonly_fields = ("cuota", "importe", "capital", "interes")
    can_delete = False


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ("folio", "fecha", "cliente", "credito", "importe", "metodo",
                    "tipo", "estado")
    list_filter = ("estado", "tipo", "metodo", "negocio")
    search_fields = ("folio", "referencia", "credito__folio")
    readonly_fields = ("folio", "importe_aplicado", "excedente", "creado_en")
    inlines = [AplicacionInline]
    date_hierarchy = "fecha"

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
