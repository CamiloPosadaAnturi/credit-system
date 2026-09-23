from django.contrib import admin

from apps.creditos.models import Credito, Cuota


class CuotaInline(admin.TabularInline):
    model = Cuota
    extra = 0
    readonly_fields = ("numero", "fecha_vencimiento", "importe_programado",
                       "capital_programado", "interes_programado",
                       "importe_pagado", "estado")
    can_delete = False


@admin.register(Credito)
class CreditoAdmin(admin.ModelAdmin):
    list_display = ("folio", "cliente", "negocio", "capital", "interes_total",
                    "total_a_pagar", "saldo_pendiente", "estado")
    list_filter = ("estado", "negocio", "frecuencia_pago", "modalidad_interes")
    search_fields = ("folio", "cliente__nombres", "cliente__apellido_paterno")
    readonly_fields = ("folio", "interes_total", "total_a_pagar", "importe_cuota",
                       "capital_pagado", "interes_pagado", "saldo_pendiente",
                       "fecha_vencimiento_final", "creado_en", "actualizado_en")
    inlines = [CuotaInline]

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Cuota)
class CuotaAdmin(admin.ModelAdmin):
    list_display = ("credito", "numero", "fecha_vencimiento", "importe_programado",
                    "importe_pagado", "estado")
    list_filter = ("estado",)
    search_fields = ("credito__folio",)

    def has_delete_permission(self, request, obj=None):
        return False
