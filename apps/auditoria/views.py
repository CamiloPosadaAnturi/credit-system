from django.views.generic import ListView

from apps.auditoria.models import RegistroAuditoria, TipoAccion
from apps.core.mixins import AccionRequeridaMixin, BusquedaMixin
from apps.usuarios import permisos


class AuditoriaListView(AccionRequeridaMixin, BusquedaMixin, ListView):
    accion = permisos.VER_AUDITORIA
    model = RegistroAuditoria
    template_name = "auditoria/lista.html"
    context_object_name = "registros"
    paginate_by = 50
    campos_busqueda = ["descripcion", "modelo", "objeto_id",
                       "usuario__username", "usuario__first_name"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("usuario", "negocio")
        if not self.request.user.es_superadmin:
            permitidos = permisos.negocios_permitidos(self.request.user)
            qs = qs.filter(negocio__in=permitidos)
        accion = self.request.GET.get("accion")
        if accion:
            qs = qs.filter(accion=accion)
        desde = self.request.GET.get("desde")
        hasta = self.request.GET.get("hasta")
        if desde:
            qs = qs.filter(fecha__date__gte=desde)
        if hasta:
            qs = qs.filter(fecha__date__lte=hasta)
        return qs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["acciones"] = TipoAccion.choices
        contexto["accion_seleccionada"] = self.request.GET.get("accion", "")
        contexto["desde"] = self.request.GET.get("desde", "")
        contexto["hasta"] = self.request.GET.get("hasta", "")
        contexto["titulo"] = "Auditoria"
        return contexto
