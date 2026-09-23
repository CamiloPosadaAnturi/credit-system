from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View

from apps.clientes.forms import ClienteForm, FiltroClienteForm, ReferenciaFormSet
from apps.clientes.models import Cliente, EstadoCliente
from apps.clientes.servicios import historial_pagos, resumen_cliente
from apps.core.mixins import AccionRequeridaMixin, AuditableMixin, BusquedaMixin
from apps.usuarios import permisos


class ClienteBaseMixin(LoginRequiredMixin):
    model = Cliente

    def get_queryset(self):
        qs = Cliente.objects.select_related("negocio", "cobrador")
        qs = permisos.filtrar_por_negocio(qs, self.request.user)
        return permisos.filtrar_cartera_cobrador(qs, self.request.user)


class ClienteListView(ClienteBaseMixin, BusquedaMixin, ListView):
    template_name = "clientes/lista.html"
    context_object_name = "clientes"
    paginate_by = 25
    campos_busqueda = ["nombres", "apellido_paterno", "apellido_materno",
                       "telefono_principal", "codigo"]

    def get_queryset(self):
        qs = super().get_queryset()
        self.formulario_filtro = FiltroClienteForm(
            self.request.GET or None, usuario=self.request.user)
        if self.formulario_filtro.is_valid():
            datos = self.formulario_filtro.cleaned_data
            if datos.get("negocio"):
                qs = qs.filter(negocio=datos["negocio"])
            if datos.get("estado"):
                qs = qs.filter(estado=datos["estado"])
            if datos.get("cobrador"):
                qs = qs.filter(cobrador=datos["cobrador"])
        return qs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["formulario_filtro"] = self.formulario_filtro
        contexto["titulo"] = "Clientes"
        return contexto


class ClienteDetailView(ClienteBaseMixin, DetailView):
    template_name = "clientes/detalle.html"
    context_object_name = "cliente"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["resumen"] = resumen_cliente(self.object)
        contexto["creditos"] = self.object.creditos.select_related("cobrador").order_by(
            "-fecha_solicitud")
        contexto["pagos"] = historial_pagos(self.object, limite=25)
        contexto["puede_ver_sensibles"] = permisos.puede(
            self.request.user, permisos.VER_DATOS_SENSIBLES)
        return contexto


class ClienteFormMixin(AuditableMixin):
    form_class = ClienteForm
    template_name = "clientes/formulario.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        if self.request.POST:
            contexto["referencias"] = ReferenciaFormSet(
                self.request.POST, instance=self.object)
        else:
            contexto["referencias"] = ReferenciaFormSet(instance=self.object)
        return contexto

    def form_valid(self, form):
        contexto = self.get_context_data()
        referencias = contexto["referencias"]
        with transaction.atomic():
            respuesta = super().form_valid(form)
            if referencias.is_valid():
                referencias.instance = self.object
                referencias.save()
            else:
                transaction.set_rollback(True)
                return self.form_invalid(form)
        return respuesta


class ClienteCreateView(AccionRequeridaMixin, ClienteFormMixin, CreateView):
    accion = permisos.GESTIONAR_CLIENTES
    model = Cliente

    def form_valid(self, form):
        permisos.exigir_negocio(self.request.user, form.cleaned_data["negocio"])
        messages.success(self.request, "Cliente registrado correctamente.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Nuevo cliente"
        return contexto


class ClienteUpdateView(AccionRequeridaMixin, ClienteFormMixin, ClienteBaseMixin, UpdateView):
    accion = permisos.GESTIONAR_CLIENTES

    def form_valid(self, form):
        permisos.exigir_negocio(self.request.user, form.cleaned_data["negocio"])
        messages.success(self.request, "Cliente actualizado.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = f"Editar {self.object}"
        return contexto


class ClienteCambiarEstadoView(AccionRequeridaMixin, View):
    accion = permisos.GESTIONAR_CLIENTES

    def post(self, request, pk):
        cliente = get_object_or_404(
            permisos.filtrar_por_negocio(Cliente.objects.all(), request.user), pk=pk)
        nuevo = request.POST.get("estado")
        if nuevo not in EstadoCliente.values:
            messages.error(request, "Estado no valido.")
        else:
            cliente.estado = nuevo
            cliente.actualizado_por = request.user
            cliente.save(update_fields=["estado", "actualizado_por", "actualizado_en"])
            messages.success(request, f"El cliente quedo como {cliente.get_estado_display()}.")
        return redirect(reverse("clientes:detalle", args=[cliente.pk]))
