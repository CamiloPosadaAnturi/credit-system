from django.contrib import admin

from apps.clientes.models import Cliente, ReferenciaPersonal


class ReferenciaInline(admin.TabularInline):
    model = ReferenciaPersonal
    extra = 0


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre_completo", "negocio", "telefono_principal",
                    "cobrador", "estado")
    list_filter = ("negocio", "estado", "cobrador")
    search_fields = ("nombres", "apellido_paterno", "apellido_materno",
                     "telefono_principal", "codigo")
    inlines = [ReferenciaInline]
    readonly_fields = ("codigo", "creado_en", "actualizado_en")
