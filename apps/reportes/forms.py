from django import forms

from apps.creditos.models import EstadoCredito
from apps.pagos.models import MetodoPago
from apps.usuarios import permisos
from apps.usuarios.models import Rol, Usuario


class FiltroReporteForm(forms.Form):
    negocio = forms.ModelChoiceField(
        label="Negocio", required=False, queryset=None, empty_label="Todos",
        widget=forms.Select(attrs={"class": "form-select"}))
    desde = forms.DateField(
        label="Desde", required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    hasta = forms.DateField(
        label="Hasta", required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    estado = forms.ChoiceField(
        label="Estado del credito", required=False,
        choices=[("", "Todos")] + list(EstadoCredito.choices),
        widget=forms.Select(attrs={"class": "form-select"}))
    cobrador = forms.ModelChoiceField(
        label="Cobrador", required=False, queryset=None, empty_label="Todos",
        widget=forms.Select(attrs={"class": "form-select"}))
    metodo = forms.ChoiceField(
        label="Metodo de pago", required=False,
        choices=[("", "Todos")] + list(MetodoPago.choices),
        widget=forms.Select(attrs={"class": "form-select"}))

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        negocios = permisos.negocios_permitidos(usuario) if usuario else None
        self.fields["negocio"].queryset = negocios
        self.fields["cobrador"].queryset = (
            Usuario.objects.filter(rol=Rol.COBRADOR, negocios__in=negocios).distinct()
            if negocios is not None else Usuario.objects.cobradores()
        )
