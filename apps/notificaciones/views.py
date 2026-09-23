from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import ListView, View

from apps.notificaciones.models import Notificacion
from apps.notificaciones.servicios import notificaciones_de


class NotificacionListView(LoginRequiredMixin, ListView):
    template_name = "notificaciones/lista.html"
    context_object_name = "notificaciones"
    paginate_by = 30

    def get_queryset(self):
        return notificaciones_de(self.request.user, solo_no_leidas=False).select_related(
            "negocio")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Notificaciones"
        return contexto


class MarcarLeidasView(LoginRequiredMixin, View):
    def post(self, request):
        notificaciones_de(request.user).update(leida=True)
        return redirect("notificaciones:lista")


class MarcarLeidaView(LoginRequiredMixin, View):
    def post(self, request, pk):
        Notificacion.objects.filter(
            pk=pk, negocio__in=request.user.negocios_permitidos()
        ).update(leida=True)
        return redirect(request.META.get("HTTP_REFERER", "notificaciones:lista"))
