from django import forms
from django.forms import inlineformset_factory

from apps.clientes.models import Cliente, EstadoCliente, ReferenciaPersonal
from apps.negocios.forms import ControlBootstrapMixin
from apps.usuarios import permisos
from apps.usuarios.models import Rol, Usuario


class ClienteForm(ControlBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Cliente
        fields = [
            "negocio", "nombres", "apellido_paterno", "apellido_materno",
            "curp", "rfc", "fecha_nacimiento",
            "telefono_principal", "telefono_alterno", "email",
            "direccion", "ciudad", "estado_republica", "codigo_postal",
            "ocupacion", "cobrador", "estado", "observaciones",
        ]
        widgets = {
            "fecha_nacimiento": forms.DateInput(attrs={"type": "date"}),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
        }

    SECCIONES = [
        ("Identificacion", ["negocio", "nombres", "apellido_paterno",
                            "apellido_materno", "fecha_nacimiento", "ocupacion"]),
        ("Documentos (acceso restringido)", ["curp", "rfc"]),
        ("Contacto", ["telefono_principal", "telefono_alterno", "email"]),
        ("Domicilio", ["direccion", "ciudad", "estado_republica", "codigo_postal"]),
        ("Operacion", ["cobrador", "estado", "observaciones"]),
    ]

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        if usuario is not None:
            self.fields["negocio"].queryset = permisos.negocios_permitidos(usuario).activos()
            self.fields["cobrador"].queryset = Usuario.objects.cobradores().filter(
                negocios__in=permisos.negocios_permitidos(usuario)
            ).distinct()
            if not permisos.puede(usuario, permisos.VER_DATOS_SENSIBLES):
                # Sin permiso no se muestran ni se editan CURP/RFC.
                self.fields.pop("curp", None)
                self.fields.pop("rfc", None)
        self.fields["cobrador"].queryset = getattr(
            self.fields["cobrador"], "queryset", Usuario.objects.cobradores()
        )
        self.aplicar_estilos()

    def clean(self):
        datos = super().clean()
        negocio = datos.get("negocio")
        cobrador = datos.get("cobrador")
        if negocio and cobrador and not cobrador.negocios.filter(pk=negocio.pk).exists():
            self.add_error(
                "cobrador",
                "El cobrador seleccionado no esta autorizado en ese negocio.",
            )
        return datos


ReferenciaFormSet = inlineformset_factory(
    Cliente, ReferenciaPersonal,
    fields=["nombre", "parentesco", "telefono", "direccion"],
    extra=1, can_delete=True,
    widgets={
        "nombre": forms.TextInput(attrs={"class": "form-control"}),
        "parentesco": forms.TextInput(attrs={"class": "form-control"}),
        "telefono": forms.TextInput(attrs={"class": "form-control"}),
        "direccion": forms.TextInput(attrs={"class": "form-control"}),
    },
)


class FiltroClienteForm(forms.Form):
    q = forms.CharField(
        label="Buscar", required=False,
        widget=forms.TextInput(attrs={"class": "form-control",
                                      "placeholder": "Nombre, telefono o codigo"}))
    negocio = forms.ModelChoiceField(
        label="Negocio", required=False, queryset=None, empty_label="Todos",
        widget=forms.Select(attrs={"class": "form-select"}))
    estado = forms.ChoiceField(
        label="Estado", required=False,
        choices=[("", "Todos")] + list(EstadoCliente.choices),
        widget=forms.Select(attrs={"class": "form-select"}))
    cobrador = forms.ModelChoiceField(
        label="Cobrador", required=False, queryset=None, empty_label="Todos",
        widget=forms.Select(attrs={"class": "form-select"}))

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        negocios = permisos.negocios_permitidos(usuario) if usuario else None
        self.fields["negocio"].queryset = negocios
        self.fields["cobrador"].queryset = (
            Usuario.objects.filter(rol=Rol.COBRADOR, negocios__in=negocios).distinct()
            if negocios is not None
            else Usuario.objects.cobradores()
        )
