from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from apps.negocios.forms import ControlBootstrapMixin
from apps.usuarios.models import Rol, Usuario


class LoginForm(ControlBootstrapMixin, AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"placeholder": "Usuario", "autofocus": True}
        )
        self.fields["password"].widget.attrs.update({"placeholder": "Contrasena"})
        self.aplicar_estilos()


class UsuarioForm(ControlBootstrapMixin, forms.ModelForm):
    """Alta y edicion de usuarios por parte de un administrador."""

    class Meta:
        model = Usuario
        fields = ["username", "first_name", "last_name", "email", "telefono",
                  "rol", "negocios", "is_active"]
        widgets = {"negocios": forms.CheckboxSelectMultiple()}

    SECCIONES = [
        ("Datos de la persona", ["first_name", "last_name", "email", "telefono"]),
        ("Acceso", ["username", "is_active"]),
        ("Rol y negocios", ["rol", "negocios"]),
    ]

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        from apps.usuarios import permisos

        if usuario is not None:
            self.fields["negocios"].queryset = permisos.negocios_permitidos(usuario)
            if not usuario.es_superadmin:
                # Un administrador de negocio no puede crear superadministradores.
                self.fields["rol"].choices = [
                    (v, e) for v, e in Rol.choices if v != Rol.SUPERADMIN
                ]
        self.fields["negocios"].required = False
        self.aplicar_estilos()
        self.fields["negocios"].widget.attrs.pop("class", None)

    def clean(self):
        datos = super().clean()
        rol = datos.get("rol")
        negocios = datos.get("negocios")
        if rol != Rol.SUPERADMIN and not negocios:
            self.add_error(
                "negocios",
                "Selecciona al menos un negocio. Sin negocio autorizado el usuario "
                "no podra ver informacion.",
            )
        return datos


class UsuarioCreacionForm(UsuarioForm, UserCreationForm):
    class Meta(UsuarioForm.Meta):
        fields = UsuarioForm.Meta.fields

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre in ("password1", "password2"):
            if nombre in self.fields:
                self.fields[nombre].widget.attrs["class"] = "form-control"


class CambiarPasswordForm(ControlBootstrapMixin, forms.Form):
    password1 = forms.CharField(label="Nueva contrasena", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirmar contrasena", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()

    def clean(self):
        datos = super().clean()
        if datos.get("password1") != datos.get("password2"):
            self.add_error("password2", "Las contrasenas no coinciden.")
        if len(datos.get("password1") or "") < 8:
            self.add_error("password1", "La contrasena debe tener al menos 8 caracteres.")
        return datos


class PerfilForm(ControlBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ["first_name", "last_name", "email", "telefono"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()
