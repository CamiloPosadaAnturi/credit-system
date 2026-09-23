from django.contrib import admin

from apps.cobranza.models import GestionCobranza


@admin.register(GestionCobranza)
class GestionCobranzaAdmin(admin.ModelAdmin):
    list_display = ("fecha", "cliente", "credito", "tipo", "resultado", "usuario")
    list_filter = ("tipo", "resultado", "negocio")
    search_fields = ("cliente__nombres", "credito__folio")
    date_hierarchy = "fecha"
