import datetime as dt

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import ListView, TemplateView, View

from apps.auditoria.models import TipoAccion
from apps.auditoria.servicios import registrar
from apps.cobranza import servicios
from apps.cobranza.forms import FiltroCobranzaForm, FiltroGestionForm, GestionForm
from apps.cobranza.models import GestionCobranza
from apps.core.fechas import hoy_local
from apps.core.mixins import AccionRequeridaMixin
from apps.creditos.models import Credito
from apps.usuarios import permisos


def creditos_autorizados(request):
    qs = permisos.filtrar_por_negocio(Credito.objects.all(), request.user)
    return permisos.filtrar_cartera_cobrador(qs, request.user)


class TableroCobranzaView(AccionRequeridaMixin, TemplateView):
    accion = permisos.VER_COBRANZA
    template_name = "cobranza/tablero.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        peticion = self.request
        formulario = FiltroCobranzaForm(peticion.GET or None, usuario=peticion.user)
        creditos = creditos_autorizados(peticion)
        atraso_minimo = 0
        if formulario.is_valid():
            datos = formulario.cleaned_data
            if datos.get("negocio"):
                creditos = creditos.filter(negocio=datos["negocio"])
            if datos.get("cobrador"):
                creditos = creditos.filter(cobrador=datos["cobrador"])
            atraso_minimo = datos.get("atraso_minimo") or 0

        hoy = hoy_local()
        vigentes = creditos.vigentes()
        contexto.update({
            "formulario_filtro": formulario,
            "hoy": hoy,
            "clasificacion": servicios.clasificacion_cartera(creditos, hoy),
            "cuotas_hoy": servicios.cuotas_que_vencen(vigentes, hoy),
            "cuotas_proximas": servicios.cuotas_proximas(vigentes, 7, hoy)[:50],
            "cuotas_vencidas": servicios.cuotas_vencidas(
                vigentes, hoy, atraso_minimo)[:100],
            "mora": servicios.resumen_mora_por_credito(vigentes, hoy)[:100],
            "titulo": "Cobranza y cartera vencida",
        })
        return contexto


class GestionListView(AccionRequeridaMixin, ListView):
    accion = permisos.VER_COBRANZA
    model = GestionCobranza
    template_name = "cobranza/gestiones.html"
    context_object_name = "gestiones"
    paginate_by = 30

    def get_queryset(self):
        qs = GestionCobranza.objects.select_related(
            "cliente", "credito", "usuario", "negocio")
        qs = permisos.filtrar_por_negocio(qs, self.request.user)
        if self.request.user.es_cobrador:
            qs = qs.filter(usuario=self.request.user)
        self.formulario_filtro = FiltroGestionForm(
            self.request.GET or None, usuario=self.request.user)
        if self.formulario_filtro.is_valid():
            datos = self.formulario_filtro.cleaned_data
            if datos.get("negocio"):
                qs = qs.filter(negocio=datos["negocio"])
            if datos.get("cobrador"):
                qs = qs.filter(usuario=datos["cobrador"])
            if datos.get("tipo"):
                qs = qs.filter(tipo=datos["tipo"])
            if datos.get("resultado"):
                qs = qs.filter(resultado=datos["resultado"])
            if datos.get("desde"):
                qs = qs.filter(fecha__date__gte=datos["desde"])
            if datos.get("hasta"):
                qs = qs.filter(fecha__date__lte=datos["hasta"])
        return qs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["formulario_filtro"] = self.formulario_filtro
        contexto["titulo"] = "Gestiones de cobranza"
        return contexto


class RegistrarGestionView(AccionRequeridaMixin, View):
    accion = permisos.REGISTRAR_GESTION
    template_name = "cobranza/registrar_gestion.html"

    def get_credito(self, request, credito_id) -> Credito:
        return get_object_or_404(
            creditos_autorizados(request).select_related("cliente", "negocio"),
            pk=credito_id)

    def get(self, request, credito_id):
        credito = self.get_credito(request, credito_id)
        return render(request, self.template_name, {
            "credito": credito,
            "form": GestionForm(initial={
                "proxima_fecha_contacto": hoy_local() + dt.timedelta(days=1)}),
            "gestiones": credito.gestiones.select_related("usuario")[:10],
        })

    def post(self, request, credito_id):
        credito = self.get_credito(request, credito_id)
        formulario = GestionForm(request.POST)
        if formulario.is_valid():
            gestion = formulario.save(commit=False)
            gestion.credito = credito
            gestion.cliente = credito.cliente
            gestion.negocio = credito.negocio
            gestion.usuario = request.user
            gestion.fecha = timezone.now()
            gestion.save()
            registrar(
                TipoAccion.GESTION,
                f"Gestion de cobranza ({gestion.get_tipo_display()}) sobre {credito.folio}",
                objeto=gestion, usuario=request.user, negocio=credito.negocio,
                datos={"resultado": gestion.resultado,
                       "monto_prometido": str(gestion.monto_prometido)},
            )
            messages.success(request, "Gestion registrada.")
            return redirect("creditos:detalle", pk=credito.pk)
        return render(request, self.template_name, {
            "credito": credito, "form": formulario,
            "gestiones": credito.gestiones.select_related("usuario")[:10],
        })


class MiCarteraView(AccionRequeridaMixin, TemplateView):
    """Vista diaria del cobrador: a quien hay que cobrar hoy."""

    accion = permisos.VER_COBRANZA
    template_name = "cobranza/mi_cartera.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        hoy = hoy_local()
        creditos = creditos_autorizados(self.request).vigentes()
        if not self.request.user.es_cobrador:
            cobrador_id = self.request.GET.get("cobrador")
            if cobrador_id:
                creditos = creditos.filter(cobrador_id=cobrador_id)
        contexto.update({
            "hoy": hoy,
            "cuotas_hoy": servicios.cuotas_que_vencen(creditos, hoy),
            "cuotas_vencidas": servicios.cuotas_vencidas(creditos, hoy),
            "cuotas_proximas": servicios.cuotas_proximas(creditos, 3, hoy),
            "titulo": "Mi cartera de hoy",
        })
        return contexto


class ActualizarMoraView(AccionRequeridaMixin, View):
    """Recalcula el estado de mora de los creditos vigentes."""

    accion = permisos.VER_COBRANZA

    def post(self, request):
        from apps.creditos.servicios import actualizar_estados_masivo

        cantidad = actualizar_estados_masivo(creditos_autorizados(request).vigentes())
        messages.success(request, f"{cantidad} credito(s) cambiaron de estado.")
        return redirect("cobranza:tablero")
