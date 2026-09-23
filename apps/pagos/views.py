import uuid

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, ListView, View

from apps.core.errores import ErrorDeNegocio
from apps.core.mixins import AccionRequeridaMixin, BusquedaMixin
from apps.creditos.models import Credito
from apps.pagos import servicios
from apps.pagos.forms import FiltroPagoForm, LiquidacionForm, PagoForm, ReversoForm
from apps.pagos.models import Pago
from apps.usuarios import permisos


class PagoBaseMixin(LoginRequiredMixin):
    model = Pago

    def get_queryset(self):
        qs = Pago.objects.select_related("credito", "cliente", "negocio",
                                         "recibido_por", "cobrador")
        qs = permisos.filtrar_por_negocio(qs, self.request.user)
        return permisos.filtrar_cartera_cobrador(qs, self.request.user)


class PagoListView(PagoBaseMixin, BusquedaMixin, ListView):
    template_name = "pagos/lista.html"
    context_object_name = "pagos"
    paginate_by = 30
    campos_busqueda = ["folio", "referencia", "cliente__nombres",
                       "cliente__apellido_paterno", "credito__folio"]

    def get_queryset(self):
        qs = super().get_queryset()
        self.formulario_filtro = FiltroPagoForm(
            self.request.GET or None, usuario=self.request.user)
        if self.formulario_filtro.is_valid():
            datos = self.formulario_filtro.cleaned_data
            if datos.get("negocio"):
                qs = qs.filter(negocio=datos["negocio"])
            if datos.get("metodo"):
                qs = qs.filter(metodo=datos["metodo"])
            if datos.get("estado"):
                qs = qs.filter(estado=datos["estado"])
            if datos.get("cobrador"):
                qs = qs.filter(cobrador=datos["cobrador"])
            if datos.get("desde"):
                qs = qs.filter(fecha__date__gte=datos["desde"])
            if datos.get("hasta"):
                qs = qs.filter(fecha__date__lte=datos["hasta"])
        return qs

    def get_context_data(self, **kwargs):
        from django.db.models import Sum

        contexto = super().get_context_data(**kwargs)
        contexto["formulario_filtro"] = self.formulario_filtro
        contexto["total_filtrado"] = (
            self.get_queryset().confirmados().aggregate(t=Sum("importe"))["t"] or 0
        )
        contexto["titulo"] = "Pagos"
        return contexto


class PagoDetailView(PagoBaseMixin, DetailView):
    template_name = "pagos/detalle.html"
    context_object_name = "pago"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["aplicaciones"] = self.object.aplicaciones.select_related("cuota")
        contexto["puede_reversar"] = (
            permisos.puede(self.request.user, permisos.REVERSAR_PAGO)
            and self.object.esta_confirmado
        )
        return contexto


def _credito_autorizado(request, credito_id) -> Credito:
    qs = permisos.filtrar_por_negocio(Credito.objects.all(), request.user)
    qs = permisos.filtrar_cartera_cobrador(qs, request.user)
    return get_object_or_404(qs.select_related("cliente", "negocio"), pk=credito_id)


class RegistrarPagoView(AccionRequeridaMixin, View):
    accion = permisos.REGISTRAR_PAGO
    template_name = "pagos/registrar.html"

    def contexto(self, request, credito, formulario):
        return {
            "credito": credito,
            "form": formulario,
            "cuotas": credito.cuotas.all(),
            "saldo_exigible": servicios.saldo_exigible(credito),
            "saldo_vencido": servicios.saldo_vencido(credito),
            "proxima_cuota": credito.proxima_cuota,
            "titulo": f"Registrar pago - {credito.folio}",
        }

    def get(self, request, credito_id):
        credito = _credito_autorizado(request, credito_id)
        inicial = {"clave_idempotencia": uuid.uuid4().hex}
        proxima = credito.proxima_cuota
        if proxima:
            inicial["importe"] = proxima.saldo
        formulario = PagoForm(initial=inicial, credito=credito)
        return render(request, self.template_name,
                      self.contexto(request, credito, formulario))

    def post(self, request, credito_id):
        credito = _credito_autorizado(request, credito_id)
        formulario = PagoForm(request.POST, credito=credito)
        if formulario.is_valid():
            datos = formulario.cleaned_data
            try:
                pago = servicios.registrar_pago(
                    credito=credito,
                    importe=datos["importe"],
                    usuario=request.user,
                    metodo=datos["metodo"],
                    fecha=datos.get("fecha") or None,
                    referencia=datos.get("referencia", ""),
                    observaciones=datos.get("observaciones", ""),
                    clave_idempotencia=datos.get("clave_idempotencia", ""),
                    permitir_excedente=datos.get("permitir_excedente", False),
                    forzar_duplicado=datos.get("confirmar_duplicado", False),
                )
            except ErrorDeNegocio as error:
                messages.error(request, str(error))
                return render(request, self.template_name,
                              self.contexto(request, credito, formulario))
            mensaje = f"Pago {pago.folio} registrado por {pago.importe} MXN."
            if pago.excedente:
                mensaje += f" Excedente no aplicado: {pago.excedente} MXN."
            messages.success(request, mensaje)
            return redirect("pagos:detalle", pk=pago.pk)
        return render(request, self.template_name,
                      self.contexto(request, credito, formulario))


class ReversarPagoView(AccionRequeridaMixin, View):
    accion = permisos.REVERSAR_PAGO
    template_name = "pagos/reversar.html"

    def get_pago(self, request, pk) -> Pago:
        qs = permisos.filtrar_por_negocio(Pago.objects.all(), request.user)
        return get_object_or_404(qs, pk=pk)

    def get(self, request, pk):
        pago = self.get_pago(request, pk)
        return render(request, self.template_name, {"pago": pago, "form": ReversoForm()})

    def post(self, request, pk):
        pago = self.get_pago(request, pk)
        formulario = ReversoForm(request.POST)
        if formulario.is_valid():
            try:
                servicios.reversar_pago(pago, request.user,
                                        formulario.cleaned_data["motivo"])
                messages.success(request, f"Pago {pago.folio} reversado.")
                return redirect("pagos:detalle", pk=pago.pk)
            except ErrorDeNegocio as error:
                messages.error(request, str(error))
        return render(request, self.template_name,
                      {"pago": pago, "form": formulario})


class LiquidarAnticipadoView(AccionRequeridaMixin, View):
    accion = permisos.REGISTRAR_PAGO
    template_name = "pagos/liquidar.html"

    def get(self, request, credito_id):
        credito = _credito_autorizado(request, credito_id)
        return render(request, self.template_name, {
            "credito": credito,
            "calculo": servicios.calcular_liquidacion_anticipada(credito),
            "form": LiquidacionForm(initial={"clave_idempotencia": uuid.uuid4().hex}),
        })

    def post(self, request, credito_id):
        credito = _credito_autorizado(request, credito_id)
        formulario = LiquidacionForm(request.POST)
        calculo = servicios.calcular_liquidacion_anticipada(credito)
        if formulario.is_valid():
            datos = formulario.cleaned_data
            try:
                pago = servicios.liquidar_anticipadamente(
                    credito, request.user,
                    metodo=datos["metodo"],
                    referencia=datos.get("referencia", ""),
                    observaciones=datos.get("observaciones", ""),
                    clave_idempotencia=datos.get("clave_idempotencia", ""),
                )
                messages.success(
                    request, f"Credito liquidado con el pago {pago.folio}.")
                return redirect("creditos:detalle", pk=credito.pk)
            except ErrorDeNegocio as error:
                messages.error(request, str(error))
        return render(request, self.template_name,
                      {"credito": credito, "calculo": calculo, "form": formulario})
