from django import forms

from apps.negocios.models import Negocio
from apps.usuarios.models import Rol, Usuario


class ControlBootstrapMixin:
    """Aplica clases de Bootstrap 5 a todos los widgets del formulario."""

    def aplicar_estilos(self):
        for campo in self.fields.values():
            widget = campo.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            elif isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("class", "form-control")
                widget.attrs.setdefault("rows", 3)
            else:
                widget.attrs.setdefault("class", "form-control")


class NegocioForm(ControlBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Negocio
        fields = [
            "nombre_comercial", "razon_social", "rfc", "telefono", "email",
            "direccion", "ciudad", "estado", "responsable", "activo",
            "modalidad_interes", "tasa_interes", "periodo_tasa",
            "frecuencia_pago", "numero_cuotas",
            "dias_gracia", "aplica_mora", "tasa_mora",
            "permite_liquidacion_anticipada", "descuento_liquidacion_anticipada",
            "observaciones",
        ]
        widgets = {
            "direccion": forms.TextInput(),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
        }

    #: Agrupacion de campos para renderizar el formulario por secciones.
    SECCIONES = [
        ("Datos generales", ["nombre_comercial", "razon_social", "rfc", "telefono",
                             "email", "responsable", "activo"]),
        ("Ubicacion", ["direccion", "ciudad", "estado"]),
        ("Configuracion de intereses", ["modalidad_interes", "tasa_interes",
                                        "periodo_tasa", "frecuencia_pago", "numero_cuotas"]),
        ("Politica de mora y liquidacion", ["dias_gracia", "aplica_mora", "tasa_mora",
                                            "permite_liquidacion_anticipada",
                                            "descuento_liquidacion_anticipada"]),
        ("Otros", ["observaciones"]),
    ]

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        self.fields["responsable"].queryset = Usuario.objects.activos().exclude(
            rol=Rol.CONSULTA
        )
        self.fields["rfc"].required = False
        self.aplicar_estilos()

    def clean_rfc(self):
        return (self.cleaned_data.get("rfc") or "").upper().strip()

    def clean(self):
        datos = super().clean()
        if datos.get("aplica_mora") and not datos.get("tasa_mora"):
            self.add_error(
                "tasa_mora",
                "Si el negocio aplica cargos moratorios debes definir la tasa diaria.",
            )
        if not datos.get("aplica_mora"):
            datos["tasa_mora"] = 0
        return datos


class FiltroNegocioForm(forms.Form):
    q = forms.CharField(
        label="Buscar", required=False,
        widget=forms.TextInput(attrs={"class": "form-control",
                                      "placeholder": "Nombre, RFC o responsable"}),
    )
    activo = forms.ChoiceField(
        label="Estado", required=False,
        choices=[("", "Todos"), ("1", "Activos"), ("0", "Inactivos")],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    desde = forms.DateField(
        label="Creado desde", required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    hasta = forms.DateField(
        label="Creado hasta", required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
