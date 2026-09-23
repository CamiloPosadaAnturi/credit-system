from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core.mixins import AccionRequeridaMixin, BusquedaMixin
from apps.usuarios import permisos
from apps.usuarios.forms import (
    CambiarPasswordForm,
    LoginForm,
    PerfilForm,
    UsuarioCreacionForm,
    UsuarioForm,
)
from apps.usuarios.models import Usuario


class EntrarView(LoginView):
    template_name = "usuarios/login.html"
    form_class = LoginForm
    redirect_authenticated_user = True


class SalirView(LogoutView):
    pass


class UsuarioListView(AccionRequeridaMixin, BusquedaMixin, ListView):
    accion = permisos.GESTIONAR_USUARIOS
    model = Usuario
    template_name = "usuarios/lista.html"
    context_object_name = "usuarios"
    paginate_by = 20
    campos_busqueda = ["username", "first_name", "last_name", "email"]

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related("negocios")
        if not self.request.user.es_superadmin:
            qs = qs.filter(
                Q(negocios__in=permisos.negocios_permitidos(self.request.user))
            ).distinct()
        rol = self.request.GET.get("rol")
        if rol:
            qs = qs.filter(rol=rol)
        return qs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        from apps.usuarios.models import Rol

        contexto["roles"] = Rol.choices
        contexto["rol_seleccionado"] = self.request.GET.get("rol", "")
        contexto["titulo"] = "Usuarios"
        return contexto


class UsuarioCreateView(AccionRequeridaMixin, CreateView):
    accion = permisos.GESTIONAR_USUARIOS
    model = Usuario
    form_class = UsuarioCreacionForm
    template_name = "usuarios/formulario.html"
    success_url = reverse_lazy("usuarios:lista")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Usuario creado correctamente.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Nuevo usuario"
        return contexto


class UsuarioUpdateView(AccionRequeridaMixin, UpdateView):
    accion = permisos.GESTIONAR_USUARIOS
    model = Usuario
    form_class = UsuarioForm
    template_name = "usuarios/formulario.html"
    success_url = reverse_lazy("usuarios:lista")

    def get_queryset(self):
        qs = Usuario.objects.all()
        if not self.request.user.es_superadmin:
            qs = qs.filter(
                negocios__in=permisos.negocios_permitidos(self.request.user)
            ).distinct()
        return qs

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Usuario actualizado.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = f"Editar {self.object}"
        return contexto


class UsuarioDetailView(AccionRequeridaMixin, DetailView):
    accion = permisos.GESTIONAR_USUARIOS
    model = Usuario
    template_name = "usuarios/detalle.html"
    context_object_name = "usuario_detalle"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        from apps.clientes.models import Cliente
        from apps.creditos.models import Credito

        contexto["clientes_asignados"] = Cliente.objects.filter(
            cobrador=self.object
        ).count()
        contexto["creditos_asignados"] = Credito.objects.filter(
            cobrador=self.object
        ).count()
        return contexto


def cambiar_password(request, pk):
    permisos.exigir(request.user, permisos.GESTIONAR_USUARIOS)
    usuario = get_object_or_404(Usuario, pk=pk)
    if not request.user.es_superadmin:
        permitidos = permisos.negocios_permitidos(request.user)
        if not usuario.negocios.filter(pk__in=permitidos).exists():
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("No puedes modificar este usuario.")
    formulario = CambiarPasswordForm(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        usuario.set_password(formulario.cleaned_data["password1"])
        usuario.save(update_fields=["password"])
        messages.success(request, f"Contrasena de {usuario} actualizada.")
        return redirect("usuarios:detalle", pk=usuario.pk)
    return render(request, "usuarios/cambiar_password.html",
                  {"form": formulario, "usuario_detalle": usuario})


class PerfilView(LoginRequiredMixin, UpdateView):
    model = Usuario
    form_class = PerfilForm
    template_name = "usuarios/perfil.html"
    success_url = reverse_lazy("usuarios:perfil")

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, "Perfil actualizado.")
        return super().form_valid(form)


def cambiar_mi_password(request):
    from django.contrib.auth.forms import PasswordChangeForm

    formulario = PasswordChangeForm(request.user, request.POST or None)
    for campo in formulario.fields.values():
        campo.widget.attrs.setdefault("class", "form-control")
    if request.method == "POST" and formulario.is_valid():
        usuario = formulario.save()
        update_session_auth_hash(request, usuario)
        messages.success(request, "Tu contrasena fue actualizada.")
        return redirect("usuarios:perfil")
    return render(request, "usuarios/cambiar_password.html",
                  {"form": formulario, "usuario_detalle": request.user, "propio": True})
