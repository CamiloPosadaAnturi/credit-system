import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.core.fechas import hoy_local
from apps.dashboard import servicios
from apps.usuarios import permisos


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/inicio.html"

    def get_periodo(self):
        hoy = hoy_local()
        desde = self.request.GET.get("desde") or hoy.replace(day=1).isoformat()
        hasta = self.request.GET.get("hasta") or hoy.isoformat()
        import datetime as dt

        try:
            return (dt.date.fromisoformat(desde), dt.date.fromisoformat(hasta))
        except ValueError:
            return (hoy.replace(day=1), hoy)

    def get_negocio(self):
        valor = self.request.GET.get("negocio")
        if not valor:
            return None
        return permisos.negocios_permitidos(self.request.user).filter(pk=valor).first()

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        usuario = self.request.user
        desde, hasta = self.get_periodo()
        negocio = self.get_negocio()

        contexto["indicadores"] = servicios.indicadores(usuario, negocio, desde, hasta)
        contexto["cobrar_hoy"] = servicios.clientes_a_cobrar_hoy(usuario, negocio)
        contexto["mora"] = servicios.clientes_en_mora(usuario, negocio)[:15]
        contexto["ranking_solicitantes"] = servicios.ranking_solicitantes(
            usuario, negocio, desde, hasta)
        contexto["ranking_pagadores"] = servicios.ranking_pagadores(
            usuario, negocio, desde, hasta)
        contexto["actividad"] = servicios.actividad_reciente(usuario, negocio)
        if permisos.puede(usuario, permisos.VER_REPORTES):
            contexto["cobradores"] = servicios.desempeno_cobradores(
                usuario, negocio, desde, hasta)
        contexto["grafico_pagos"] = json.dumps(
            servicios.pagos_vs_programado(usuario, negocio))
        contexto["grafico_cartera"] = json.dumps(
            servicios.composicion_cartera(usuario, negocio))
        contexto["serie_pagos"] = json.dumps(servicios.serie_pagos(usuario, negocio))
        contexto["desde"] = desde.isoformat()
        contexto["hasta"] = hasta.isoformat()
        contexto["negocio_seleccionado"] = negocio
        contexto["titulo"] = "Dashboard"
        return contexto
