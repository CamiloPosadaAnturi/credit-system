"""Mixins de vistas: autenticacion, permisos por rol y aislamiento por negocio."""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from apps.usuarios import permisos


class AccionRequeridaMixin(LoginRequiredMixin):
    """Exige que el usuario pueda ejecutar ``accion`` (matriz de permisos)."""

    accion: str | None = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if self.accion and not permisos.puede(request.user, self.accion):
            raise PermissionDenied("No tienes autorizacion para esta operacion.")
        return super().dispatch(request, *args, **kwargs)


class NegocioScopedMixin:
    """Restringe el queryset a los negocios autorizados del usuario.

    ``campo_negocio`` es la ruta ORM hacia el negocio desde el modelo
    de la vista (por ejemplo ``"credito__negocio"``).
    """

    campo_negocio: str = "negocio"
    campo_cobrador: str | None = None

    def get_queryset(self):
        qs = super().get_queryset()
        qs = permisos.filtrar_por_negocio(qs, self.request.user, self.campo_negocio)
        if self.campo_cobrador:
            qs = permisos.filtrar_cartera_cobrador(qs, self.request.user, self.campo_cobrador)
        return qs


class NegocioActivoMixin:
    """Expone el negocio seleccionado en la barra superior (parametro ?negocio=)."""

    def get_negocio_seleccionado(self):
        negocios = permisos.negocios_permitidos(self.request.user)
        valor = self.request.GET.get("negocio")
        if valor:
            return negocios.filter(pk=valor).first()
        return None

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["negocio_seleccionado"] = self.get_negocio_seleccionado()
        contexto["negocios_disponibles"] = permisos.negocios_permitidos(self.request.user)
        return contexto


class BusquedaMixin:
    """Busqueda simple por ?q= sobre ``campos_busqueda``."""

    campos_busqueda: list[str] = []

    def get_queryset(self):
        qs = super().get_queryset()
        termino = (self.request.GET.get("q") or "").strip()
        if termino and self.campos_busqueda:
            from django.db.models import Q

            filtro = Q()
            for campo in self.campos_busqueda:
                filtro |= Q(**{f"{campo}__icontains": termino})
            qs = qs.filter(filtro)
        return qs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["q"] = self.request.GET.get("q", "")
        contexto["querystring"] = self.querystring_sin_pagina()
        return contexto

    def querystring_sin_pagina(self) -> str:
        parametros = self.request.GET.copy()
        parametros.pop("page", None)
        return parametros.urlencode()


class AuditableMixin:
    """Guarda quien crea y quien modifica el registro."""

    def form_valid(self, form):
        if not form.instance.pk:
            form.instance.creado_por = self.request.user
        form.instance.actualizado_por = self.request.user
        return super().form_valid(form)


def exigir_acceso_a_negocio(usuario, negocio) -> None:
    if negocio is None:
        raise PermissionDenied("Operacion sin negocio asociado.")
    permisos.exigir_negocio(usuario, negocio)
