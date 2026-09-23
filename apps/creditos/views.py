import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, ListView, UpdateView, View

from apps.core.dinero import a_decimal
from apps.core.errores import ErrorDeNegocio
from apps.core.fechas import hoy_local
from apps.core.mixins import AccionRequeridaMixin, BusquedaMixin
from apps.creditos import servicios
from apps.creditos.calculos import simular
from apps.creditos.forms import (
    CancelacionForm,
    CreditoForm,
    FiltroCreditoForm,
    ReestructuracionForm,
)
from apps.creditos.models import ESTADOS_EDITABLES, Credito, EstadoCredito
from apps.usuarios import permisos


class CreditoBaseMixin(LoginRequiredMixin):
    model = Credito

    def get_queryset(self):
        qs = Credito.objects.select_related("cliente", "negocio", "cobrador")
        qs = permisos.filtrar_por_negocio(qs, self.request.user)
        return permisos.filtrar_cartera_cobrador(qs, self.request.user)


class CreditoListView(CreditoBaseMixin, BusquedaMixin, ListView):
    template_name = "creditos/lista.html"
    context_object_name = "creditos"
    paginate_by = 25
    campos_busqueda = ["folio", "cliente__nombres", "cliente__apellido_paterno",
                       "cliente__apellido_materno"]

    def get_queryset(self):
        qs = super().get_queryset()
        self.formulario_filtro = FiltroCreditoForm(
            self.request.GET or None, usuario=self.request.user)
        if self.formulario_filtro.is_valid():
            datos = self.formulario_filtro.cleaned_data
            if datos.get("negocio"):
                qs = qs.filter(negocio=datos["negocio"])
            if datos.get("estado"):
                qs = qs.filter(estado=datos["estado"])
            if datos.get("cobrador"):
                qs = qs.filter(cobrador=datos["cobrador"])
            if datos.get("desde"):
                qs = qs.filter(fecha_desembolso__gte=datos["desde"])
            if datos.get("hasta"):
                qs = qs.filter(fecha_desembolso__lte=datos["hasta"])
        return qs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["formulario_filtro"] = self.formulario_filtro
        contexto["titulo"] = "Creditos"
        return contexto


class CreditoDetailView(CreditoBaseMixin, DetailView):
    template_name = "creditos/detalle.html"
    context_object_name = "credito"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        credito = self.object
        contexto["cuotas"] = credito.cuotas.all()
        contexto["pagos"] = credito.pagos.select_related("recibido_por").order_by("-fecha")
        contexto["puede_aprobar"] = (
            permisos.puede(self.request.user, permisos.APROBAR_CREDITO)
            and credito.estado in ESTADOS_EDITABLES
        )
        contexto["puede_desembolsar"] = (
            permisos.puede(self.request.user, permisos.DESEMBOLSAR_CREDITO)
            and credito.estado == EstadoCredito.APROBADO
        )
        contexto["puede_registrar_pago"] = (
            permisos.puede(self.request.user, permisos.REGISTRAR_PAGO)
            and credito.esta_vigente
        )
        contexto["puede_cancelar"] = (
            permisos.puede(self.request.user, permisos.CANCELAR_CREDITO)
            and credito.estado not in (EstadoCredito.LIQUIDADO, EstadoCredito.CANCELADO)
        )
        contexto["puede_reestructurar"] = (
            permisos.puede(self.request.user, permisos.REESTRUCTURAR_CREDITO)
            and credito.esta_vigente
        )
        return contexto


class CreditoCrearView(AccionRequeridaMixin, View):
    """Alta de credito en dos pasos: capturar condiciones y confirmar."""

    accion = permisos.CREAR_CREDITO
    template_name = "creditos/formulario.html"

    def get(self, request):
        inicial = {"fecha_solicitud": hoy_local(), "fecha_primer_pago": hoy_local()}
        cliente_id = request.GET.get("cliente")
        if cliente_id:
            from apps.clientes.models import Cliente

            cliente = get_object_or_404(
                permisos.filtrar_por_negocio(Cliente.objects.all(), request.user),
                pk=cliente_id,
            )
            inicial.update({"cliente": cliente.pk, "negocio": cliente.negocio_id,
                            "cobrador": cliente.cobrador_id,
                            "modalidad_interes": cliente.negocio.modalidad_interes,
                            "tasa_interes": cliente.negocio.tasa_interes,
                            "periodo_tasa": cliente.negocio.periodo_tasa,
                            "frecuencia_pago": cliente.negocio.frecuencia_pago,
                            "numero_cuotas": cliente.negocio.numero_cuotas})
        formulario = CreditoForm(initial=inicial, usuario=request.user)
        return render(request, self.template_name,
                      {"form": formulario, "titulo": "Nuevo credito"})

    def post(self, request):
        formulario = CreditoForm(request.POST, request.FILES, usuario=request.user)
        if not formulario.is_valid():
            return render(request, self.template_name,
                          {"form": formulario, "titulo": "Nuevo credito"})

        datos = formulario.cleaned_data
        permisos.exigir_negocio(request.user, datos["negocio"])
        simulacion = simular(
            capital=datos["capital"],
            modalidad=datos["modalidad_interes"],
            tasa=datos["tasa_interes"] or 0,
            numero_cuotas=datos["numero_cuotas"],
            fecha_primer_pago=datos["fecha_primer_pago"],
            frecuencia=datos["frecuencia_pago"],
            dias_personalizados=datos.get("dias_personalizados"),
        )

        if request.POST.get("confirmar") != "1":
            from apps.creditos.servicios import resumen_para_nuevo_credito

            return render(request, "creditos/confirmar.html", {
                "form": formulario,
                "simulacion": simulacion,
                "cliente": datos["cliente"],
                "resumen_cliente": resumen_para_nuevo_credito(datos["cliente"]),
                "titulo": "Confirmar condiciones del credito",
            })

        try:
            credito = servicios.crear_credito(
                cliente=datos["cliente"],
                negocio=datos["negocio"],
                capital=datos["capital"],
                numero_cuotas=datos["numero_cuotas"],
                frecuencia=datos["frecuencia_pago"],
                fecha_primer_pago=datos["fecha_primer_pago"],
                usuario=request.user,
                cobrador=datos.get("cobrador"),
                modalidad_interes=datos["modalidad_interes"],
                tasa_interes=datos["tasa_interes"] or 0,
                periodo_tasa=datos["periodo_tasa"],
                dias_personalizados=datos.get("dias_personalizados"),
                fecha_solicitud=datos["fecha_solicitud"],
                observaciones=datos.get("observaciones", ""),
            )
        except ErrorDeNegocio as error:
            messages.error(request, str(error))
            return render(request, self.template_name,
                          {"form": formulario, "titulo": "Nuevo credito"})

        if formulario.cleaned_data.get("contrato"):
            credito.contrato = formulario.cleaned_data["contrato"]
            credito.save(update_fields=["contrato"])
        messages.success(request, f"Credito {credito.folio} creado.")
        return redirect(credito.get_absolute_url())


class CreditoEditarView(AccionRequeridaMixin, CreditoBaseMixin, UpdateView):
    accion = permisos.CREAR_CREDITO
    form_class = CreditoForm
    template_name = "creditos/formulario.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs

    def dispatch(self, request, *args, **kwargs):
        respuesta = super().dispatch(request, *args, **kwargs)
        return respuesta

    def get_object(self, queryset=None):
        credito = super().get_object(queryset)
        if not credito.es_editable:
            raise PermissionDenied(
                "Un credito desembolsado no se edita. Usa una reestructuracion "
                "autorizada o un reverso de pago."
            )
        return credito

    def form_valid(self, form):
        credito = form.save(commit=False)
        credito.actualizado_por = self.request.user
        credito.save()
        servicios.recalcular_condiciones(credito, usuario=self.request.user)
        messages.success(self.request, "Condiciones actualizadas y calendario regenerado.")
        return redirect(credito.get_absolute_url())

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = f"Editar {self.object.folio}"
        return contexto


class AccionCreditoView(LoginRequiredMixin, View):
    """Base para las transiciones de estado (POST + confirmacion)."""

    accion_permiso: str = ""

    def get_credito(self, request, pk) -> Credito:
        qs = permisos.filtrar_por_negocio(Credito.objects.all(), request.user)
        credito = get_object_or_404(qs, pk=pk)
        permisos.exigir(request.user, self.accion_permiso)
        return credito


class AprobarCreditoView(AccionCreditoView):
    accion_permiso = permisos.APROBAR_CREDITO

    def post(self, request, pk):
        credito = self.get_credito(request, pk)
        try:
            servicios.aprobar_credito(credito, request.user)
            messages.success(request, f"Credito {credito.folio} aprobado.")
        except ErrorDeNegocio as error:
            messages.error(request, str(error))
        return redirect(credito.get_absolute_url())


class DesembolsarCreditoView(AccionCreditoView):
    accion_permiso = permisos.DESEMBOLSAR_CREDITO

    def post(self, request, pk):
        credito = self.get_credito(request, pk)
        try:
            servicios.desembolsar_credito(credito, request.user)
            messages.success(
                request, f"Credito {credito.folio} desembolsado. El calendario esta activo.")
        except ErrorDeNegocio as error:
            messages.error(request, str(error))
        return redirect(credito.get_absolute_url())


class CancelarCreditoView(AccionCreditoView):
    accion_permiso = permisos.CANCELAR_CREDITO

    def get(self, request, pk):
        credito = self.get_credito(request, pk)
        return render(request, "creditos/cancelar.html",
                      {"credito": credito, "form": CancelacionForm()})

    def post(self, request, pk):
        credito = self.get_credito(request, pk)
        formulario = CancelacionForm(request.POST)
        if formulario.is_valid():
            try:
                servicios.cancelar_credito(
                    credito, request.user, formulario.cleaned_data["motivo"])
                messages.success(request, f"Credito {credito.folio} cancelado.")
                return redirect(credito.get_absolute_url())
            except ErrorDeNegocio as error:
                messages.error(request, str(error))
        return render(request, "creditos/cancelar.html",
                      {"credito": credito, "form": formulario})


class ReestructurarCreditoView(AccionCreditoView):
    accion_permiso = permisos.REESTRUCTURAR_CREDITO

    def get(self, request, pk):
        credito = self.get_credito(request, pk)
        inicial = {"numero_cuotas": credito.numero_cuotas,
                   "frecuencia_pago": credito.frecuencia_pago,
                   "fecha_primer_pago": hoy_local()}
        return render(request, "creditos/reestructurar.html",
                      {"credito": credito, "form": ReestructuracionForm(initial=inicial)})

    def post(self, request, pk):
        credito = self.get_credito(request, pk)
        formulario = ReestructuracionForm(request.POST)
        if formulario.is_valid():
            datos = formulario.cleaned_data
            try:
                nuevo = servicios.reestructurar_credito(
                    credito, request.user,
                    numero_cuotas=datos["numero_cuotas"],
                    frecuencia=datos["frecuencia_pago"],
                    fecha_primer_pago=datos["fecha_primer_pago"],
                    modalidad_interes=datos.get("modalidad_interes") or None,
                    tasa_interes=datos.get("tasa_interes"),
                    observaciones=datos.get("observaciones", ""),
                )
                messages.success(
                    request, f"Credito reestructurado. Nuevo folio: {nuevo.folio}")
                return redirect(nuevo.get_absolute_url())
            except ErrorDeNegocio as error:
                messages.error(request, str(error))
        return render(request, "creditos/reestructurar.html",
                      {"credito": credito, "form": formulario})


class CalendarioView(CreditoBaseMixin, DetailView):
    template_name = "creditos/calendario.html"
    context_object_name = "credito"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["cuotas"] = self.object.cuotas.all()
        return contexto


def simular_credito(request):
    """Previsualizacion en vivo de las condiciones (JSON).

    El resultado es informativo: el backend vuelve a calcular todo al
    guardar. Nunca se confia en numeros enviados desde el navegador.
    """
    if not request.user.is_authenticated:
        raise PermissionDenied
    try:
        datos = json.loads(request.body or "{}")
        resultado = simular(
            capital=a_decimal(datos.get("capital")),
            modalidad=datos.get("modalidad_interes"),
            tasa=a_decimal(datos.get("tasa_interes")),
            numero_cuotas=int(datos.get("numero_cuotas") or 1),
            fecha_primer_pago=hoy_local(),
            frecuencia=datos.get("frecuencia_pago"),
            dias_personalizados=int(datos.get("dias_personalizados") or 0) or None,
        )
    except (ValueError, TypeError, KeyError) as error:
        return JsonResponse({"error": str(error)}, status=400)
    return JsonResponse({
        "capital": str(resultado["capital"]),
        "interes_total": str(resultado["interes_total"]),
        "total_a_pagar": str(resultado["total_a_pagar"]),
        "importe_cuota": str(resultado["importe_cuota"]),
        "importe_ultima_cuota": str(resultado["importe_ultima_cuota"]),
        "numero_cuotas": resultado["numero_cuotas"],
    })
