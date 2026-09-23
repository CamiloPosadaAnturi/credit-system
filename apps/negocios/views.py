from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View

from apps.core.mixins import AccionRequeridaMixin, AuditableMixin, BusquedaMixin
from apps.negocios.forms import FiltroNegocioForm, NegocioForm
from apps.negocios.models import Negocio
from apps.negocios.servicios import resumen_negocio
from apps.usuarios import permisos


class NegocioBaseMixin(LoginRequiredMixin):
    model = Negocio

    def get_queryset(self):
        return permisos.negocios_permitidos(self.request.user).select_related("responsable")


class NegocioListView(NegocioBaseMixin, BusquedaMixin, ListView):
    template_name = "negocios/lista.html"
    context_object_name = "negocios"
    paginate_by = 20
    campos_busqueda = ["nombre_comercial", "razon_social", "rfc",
                       "responsable__first_name", "responsable__last_name",
                       "responsable__username"]

    def get_queryset(self):
        qs = super().get_queryset()
        formulario = FiltroNegocioForm(self.request.GET or None)
        if formulario.is_valid():
            datos = formulario.cleaned_data
            if datos.get("activo") == "1":
                qs = qs.filter(activo=True)
            elif datos.get("activo") == "0":
                qs = qs.filter(activo=False)
            if datos.get("desde"):
                qs = qs.filter(creado_en__date__gte=datos["desde"])
            if datos.get("hasta"):
                qs = qs.filter(creado_en__date__lte=datos["hasta"])
        self.formulario_filtro = formulario
        return qs.order_by("nombre_comercial")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["formulario_filtro"] = self.formulario_filtro
        contexto["titulo"] = "Negocios y sucursales"
        return contexto


class NegocioDetailView(NegocioBaseMixin, DetailView):
    template_name = "negocios/detalle.html"
    context_object_name = "negocio"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["resumen"] = resumen_negocio(self.object)
        from apps.creditos.models import Credito

        contexto["creditos_recientes"] = (
            Credito.objects.filter(negocio=self.object)
            .select_related("cliente")
            .order_by("-creado_en")[:10]
        )
        contexto["usuarios_negocio"] = self.object.usuarios.filter(is_active=True)
        return contexto


class NegocioCreateView(AccionRequeridaMixin, AuditableMixin, CreateView):
    accion = permisos.GESTIONAR_NEGOCIOS
    model = Negocio
    form_class = NegocioForm
    template_name = "negocios/formulario.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        # Quien crea el negocio queda autorizado sobre el, salvo superadmin
        # que ya ve toda la plataforma.
        if not self.request.user.es_superadmin:
            self.request.user.negocios.add(self.object)
        messages.success(self.request, f"Negocio '{self.object}' creado correctamente.")
        return respuesta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Nuevo negocio"
        return contexto


class NegocioUpdateView(AccionRequeridaMixin, AuditableMixin, UpdateView):
    accion = permisos.GESTIONAR_NEGOCIOS
    model = Negocio
    form_class = NegocioForm
    template_name = "negocios/formulario.html"

    def get_queryset(self):
        return permisos.negocios_permitidos(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Negocio actualizado correctamente.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = f"Editar {self.object}"
        return contexto


class NegocioDesactivarView(AccionRequeridaMixin, View):
    """Desactivacion segura: nunca elimina el historial financiero."""

    accion = permisos.GESTIONAR_NEGOCIOS

    def post(self, request, pk):
        negocio = get_object_or_404(permisos.negocios_permitidos(request.user), pk=pk)
        negocio.activo = not negocio.activo
        negocio.actualizado_por = request.user
        negocio.save(update_fields=["activo", "actualizado_por", "actualizado_en"])
        estado = "activado" if negocio.activo else "desactivado"
        messages.success(request, f"El negocio '{negocio}' fue {estado}.")
        return redirect("negocios:detalle", pk=negocio.pk)


class NegocioDashboardView(NegocioBaseMixin, DetailView):
    """Dashboard independiente por negocio."""

    template_name = "negocios/dashboard.html"
    context_object_name = "negocio"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        desde = self.request.GET.get("desde") or None
        hasta = self.request.GET.get("hasta") or None
        contexto["resumen"] = resumen_negocio(self.object, desde=desde, hasta=hasta)
        contexto["desde"] = desde or ""
        contexto["hasta"] = hasta or ""
        return contexto


lista = NegocioListView.as_view()
detalle = NegocioDetailView.as_view()
crear = NegocioCreateView.as_view()
editar = NegocioUpdateView.as_view()
desactivar = NegocioDesactivarView.as_view()
dashboard = NegocioDashboardView.as_view()

