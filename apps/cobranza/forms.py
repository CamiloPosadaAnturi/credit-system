from django import forms

from apps.cobranza.models import GestionCobranza, ResultadoGestion, TipoGestion
from apps.negocios.forms import ControlBootstrapMixin
from apps.usuarios import permisos
from apps.usuarios.models import Rol, Usuario


class GestionForm(ControlBootstrapMixin, forms.ModelForm):
    class Meta:
        model = GestionCobranza
        fields = ["tipo", "resultado", "monto_prometido", "fecha_promesa",
                  "proxima_fecha_contacto", "observaciones"]
        widgets = {
            "fecha_promesa": forms.DateInput(attrs={"type": "date"}),
            "proxima_fecha_contacto": forms.DateInput(attrs={"type": "date"}),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
            "monto_prometido": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()

    def clean(self):
        datos = super().clean()
        tipo = datos.get("tipo")
        if tipo in (TipoGestion.PROMESA, TipoGestion.ACUERDO):
            if not datos.get("fecha_promesa"):
                self.add_error("fecha_promesa",
                               "Indica para que fecha se comprometio el cliente.")
            if not datos.get("monto_prometido"):
                self.add_error("monto_prometido", "Indica el monto prometido.")
        return datos


class FiltroCobranzaForm(forms.Form):
    negocio = forms.ModelChoiceField(
        label="Negocio", required=False, queryset=None, empty_label="Todos",
        widget=forms.Select(attrs={"class": "form-select"}))
    cobrador = forms.ModelChoiceField(
        label="Cobrador", required=False, queryset=None, empty_label="Todos",
        widget=forms.Select(attrs={"class": "form-select"}))
    desde = forms.DateField(
        label="Desde", required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    hasta = forms.DateField(
        label="Hasta", required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    atraso_minimo = forms.IntegerField(
        label="Atraso minimo (dias)", required=False, min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "0"}))

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        negocios = permisos.negocios_permitidos(usuario) if usuario else None
        self.fields["negocio"].queryset = negocios
        self.fields["cobrador"].queryset = (
            Usuario.objects.filter(rol=Rol.COBRADOR, negocios__in=negocios).distinct()
            if negocios is not None else Usuario.objects.cobradores()
        )


class FiltroGestionForm(FiltroCobranzaForm):
    tipo = forms.ChoiceField(
        label="Tipo", required=False,
        choices=[("", "Todos")] + list(TipoGestion.choices),
        widget=forms.Select(attrs={"class": "form-select"}))
    resultado = forms.ChoiceField(
        label="Resultado", required=False,
        choices=[("", "Todos")] + list(ResultadoGestion.choices),
        widget=forms.Select(attrs={"class": "form-select"}))
