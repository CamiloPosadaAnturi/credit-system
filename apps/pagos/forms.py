from django import forms

from apps.negocios.forms import ControlBootstrapMixin
from apps.pagos.models import EstadoPago, MetodoPago
from apps.usuarios import permisos
from apps.usuarios.models import Rol, Usuario


class PagoForm(ControlBootstrapMixin, forms.Form):
    """Captura de un abono. El calculo y la aplicacion los hace el servicio."""

    importe = forms.DecimalField(
        label="Importe recibido (MXN)", max_digits=12, decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={"step": "0.01", "autofocus": True}))
    metodo = forms.ChoiceField(label="Metodo de pago", choices=MetodoPago.choices)
    fecha = forms.DateTimeField(
        label="Fecha y hora del pago", required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        help_text="Deja vacio para usar la fecha y hora actuales.")
    referencia = forms.CharField(label="Referencia", max_length=80, required=False)
    observaciones = forms.CharField(
        label="Observaciones", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    permitir_excedente = forms.BooleanField(
        label="Autorizo registrar un importe mayor al saldo (excedente)",
        required=False)
    confirmar_duplicado = forms.BooleanField(
        label="Confirmo que no es un pago duplicado", required=False)
    clave_idempotencia = forms.CharField(widget=forms.HiddenInput, required=False)

    def __init__(self, *args, credito=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.credito = credito
        self.aplicar_estilos()

    def clean_importe(self):
        importe = self.cleaned_data["importe"]
        if importe <= 0:
            raise forms.ValidationError("El importe debe ser mayor que cero.")
        return importe


class ReversoForm(ControlBootstrapMixin, forms.Form):
    motivo = forms.CharField(
        label="Motivo del reverso", max_length=255,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Queda registrado en la auditoria. El pago original no se elimina.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()


class LiquidacionForm(ControlBootstrapMixin, forms.Form):
    metodo = forms.ChoiceField(label="Metodo de pago", choices=MetodoPago.choices)
    referencia = forms.CharField(label="Referencia", max_length=80, required=False)
    observaciones = forms.CharField(
        label="Observaciones", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    clave_idempotencia = forms.CharField(widget=forms.HiddenInput, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()


class FiltroPagoForm(forms.Form):
    q = forms.CharField(
        label="Buscar", required=False,
        widget=forms.TextInput(attrs={"class": "form-control",
                                      "placeholder": "Folio, cliente o referencia"}))
    negocio = forms.ModelChoiceField(
        label="Negocio", required=False, queryset=None, empty_label="Todos",
        widget=forms.Select(attrs={"class": "form-select"}))
    metodo = forms.ChoiceField(
        label="Metodo", required=False,
        choices=[("", "Todos")] + list(MetodoPago.choices),
        widget=forms.Select(attrs={"class": "form-select"}))
    estado = forms.ChoiceField(
        label="Estado", required=False,
        choices=[("", "Todos")] + list(EstadoPago.choices),
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

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        negocios = permisos.negocios_permitidos(usuario) if usuario else None
        self.fields["negocio"].queryset = negocios
        self.fields["cobrador"].queryset = (
            Usuario.objects.filter(rol=Rol.COBRADOR, negocios__in=negocios).distinct()
            if negocios is not None else Usuario.objects.cobradores()
        )
