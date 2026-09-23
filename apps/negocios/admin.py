from django.contrib import admin

from apps.negocios.models import Negocio


@admin.register(Negocio)
class NegocioAdmin(admin.ModelAdmin):
    list_display = ("nombre_comercial", "rfc", "ciudad", "estado", "responsable",
                    "tasa_porcentaje", "activo")
    list_filter = ("activo", "estado", "modalidad_interes", "frecuencia_pago")
    search_fields = ("nombre_comercial", "razon_social", "rfc")
    readonly_fields = ("creado_en", "actualizado_en")
    fieldsets = (
        ("Datos generales", {"fields": ("nombre_comercial", "razon_social", "rfc",
                                        "telefono", "email", "responsable", "activo")}),
        ("Ubicacion", {"fields": ("direccion", "ciudad", "estado")}),
        ("Intereses", {"fields": ("modalidad_interes", "tasa_interes", "periodo_tasa",
                                  "frecuencia_pago", "numero_cuotas")}),
        ("Mora y liquidacion", {"fields": ("dias_gracia", "aplica_mora", "tasa_mora",
                                           "permite_liquidacion_anticipada",
                                           "descuento_liquidacion_anticipada")}),
        ("Otros", {"fields": ("observaciones", "creado_en", "actualizado_en")}),
    )
