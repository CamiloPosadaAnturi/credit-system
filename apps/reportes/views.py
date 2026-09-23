from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.generic import TemplateView, View

from apps.auditoria.models import TipoAccion
from apps.auditoria.servicios import registrar
from apps.core.mixins import AccionRequeridaMixin
from apps.reportes.definiciones import REPORTES
from apps.reportes.exportadores import EXPORTADORES
from apps.reportes.forms import FiltroReporteForm
from apps.usuarios import permisos

LIMITE_VISTA = 500


class CatalogoReportesView(AccionRequeridaMixin, TemplateView):
    accion = permisos.VER_REPORTES
    template_name = "reportes/catalogo.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["reportes"] = list(REPORTES.values())
        contexto["titulo"] = "Reportes"
        return contexto


class ReporteView(AccionRequeridaMixin, View):
    accion = permisos.VER_REPORTES
    template_name = "reportes/detalle.html"

    def get(self, request, clave):
        reporte = REPORTES.get(clave)
        if not reporte:
            raise Http404("Reporte no encontrado")
        formulario = FiltroReporteForm(request.GET or None, usuario=request.user)
        filtros = formulario.cleaned_data if formulario.is_valid() else {}

        formato = request.GET.get("formato")
        if formato:
            return self.exportar(request, reporte, filtros, formato)

        filas = list(reporte.generador(request.user, filtros))
        return render(request, self.template_name, {
            "reporte": reporte,
            "form": formulario,
            "filas": filas[:LIMITE_VISTA],
            "total_filas": len(filas),
            "limite": LIMITE_VISTA,
            "querystring": request.GET.urlencode(),
            "titulo": reporte.nombre,
        })

    def exportar(self, request, reporte, filtros, formato):
        exportador = EXPORTADORES.get(formato)
        if not exportador:
            messages.error(request, "Formato de exportacion no soportado.")
            return redirect("reportes:detalle", clave=reporte.clave)
        filas = list(reporte.generador(request.user, filtros))
        try:
            respuesta = exportador(reporte, filas)
        except NotImplementedError as error:
            messages.warning(request, str(error))
            return redirect("reportes:detalle", clave=reporte.clave)
        registrar(
            TipoAccion.EXPORTAR,
            f"Exporto el reporte '{reporte.nombre}' en formato {formato}",
            usuario=request.user,
            negocio=filtros.get("negocio"),
            datos={"filas": len(filas), "filtros": {
                clave: str(valor) for clave, valor in filtros.items() if valor}},
        )
        return respuesta
