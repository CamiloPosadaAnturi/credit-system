from django import forms

from apps.clientes.models import Cliente
from apps.core.opciones import FrecuenciaPago, ModalidadInteres
from apps.creditos.models import Credito, EstadoCredito
from apps.negocios.forms import ControlBootstrapMixin
from apps.usuarios import permisos
from apps.usuarios.models import Rol, Usuario


class CreditoForm(ControlBootstrapMixin, forms.ModelForm):
    """Condiciones de un credito.

    El interes, el total y el calendario NO se capturan: los calcula la
    capa de servicios a partir de estas condiciones.
    """

    class Meta:
        model = Credito
        fields = [
            "negocio", "cliente", "cobrador", "fecha_solicitud", "capital",
            "modalidad_interes", "tasa_interes", "periodo_tasa",
            "frecuencia_pago", "dias_personalizados", "numero_cuotas",
            "fecha_primer_pago", "observaciones", "contrato",
        ]
        widgets = {
            "fecha_solicitud": forms.DateInput(attrs={"type": "date"}),
            "fecha_primer_pago": forms.DateInput(attrs={"type": "date"}),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
            "capital": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "tasa_interes": forms.NumberInput(attrs={"step": "0.0001", "min": "0"}),
        }

    SECCIONES = [
        ("Solicitud", ["negocio", "cliente", "cobrador", "fecha_solicitud"]),
        ("Condiciones financieras", ["capital", "modalidad_interes", "tasa_interes",
                                     "periodo_tasa"]),
        ("Calendario", ["frecuencia_pago", "numero_cuotas", "dias_personalizados",
                        "fecha_primer_pago"]),
        ("Documentos", ["observaciones", "contrato"]),
    ]

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        negocios = permisos.negocios_permitidos(usuario) if usuario else None
        if negocios is not None:
            self.fields["negocio"].queryset = negocios.activos()
            self.fields["cliente"].queryset = (
                Cliente.objects.filter(negocio__in=negocios).activos()
                .select_related("negocio")
            )
            self.fields["cobrador"].queryset = (
                Usuario.objects.filter(rol=Rol.COBRADOR, negocios__in=negocios)
                .distinct()
            )
        self.fields["dias_personalizados"].help_text = (
            "Solo para frecuencia personalizada."
        )
        self.fields["tasa_interes"].help_text = (
            "Tanto por uno. 0.40 = 40% (400 MXN por cada 1,000 MXN prestados)."
        )
        self.aplicar_estilos()

    def clean(self):
        datos = super().clean()
        negocio = datos.get("negocio")
        cliente = datos.get("cliente")
        frecuencia = datos.get("frecuencia_pago")
        dias = datos.get("dias_personalizados")
        capital = datos.get("capital")
        cuotas = datos.get("numero_cuotas")

        if negocio and cliente and cliente.negocio_id != negocio.pk:
            self.add_error("cliente", "El cliente no pertenece al negocio seleccionado.")
        if frecuencia == FrecuenciaPago.PERSONALIZADO and not dias:
            self.add_error("dias_personalizados",
                           "Indica cada cuantos dias vence una cuota.")
        if capital is not None and capital <= 0:
            self.add_error("capital", "El capital debe ser mayor que cero.")
        if cuotas is not None and cuotas < 1:
            self.add_error("numero_cuotas", "Debe haber al menos una cuota.")
        if datos.get("modalidad_interes") != ModalidadInteres.SIN_INTERES:
            if datos.get("tasa_interes") in (None, ""):
                self.add_error("tasa_interes", "Indica la tasa aplicada.")
        return datos


class FiltroCreditoForm(forms.Form):
    q = forms.CharField(
        label="Buscar", required=False,
        widget=forms.TextInput(attrs={"class": "form-control",
                                      "placeholder": "Folio o cliente"}))
    negocio = forms.ModelChoiceField(
        label="Negocio", required=False, queryset=None, empty_label="Todos",
        widget=forms.Select(attrs={"class": "form-select"}))
    estado = forms.ChoiceField(
        label="Estado", required=False,
        choices=[("", "Todos")] + list(EstadoCredito.choices),
        widget=forms.Select(attrs={"class": "form-select"}))
    cobrador = forms.ModelChoiceField(
        label="Cobrador", required=False, queryset=None, empty_label="Todos",
        widget=forms.Select(attrs={"class": "form-select"}))
    desde = forms.DateField(
        label="Desembolso desde", required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    hasta = forms.DateField(
        label="Desembolso hasta", required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        negocios = permisos.negocios_permitidos(usuario) if usuario else None
        self.fields["negocio"].queryset = negocios
        self.fields["cobrador"].queryset = (
            Usuario.objects.filter(rol=Rol.COBRADOR, negocios__in=negocios).distinct()
            if negocios is not None else Usuario.objects.cobradores()
        )


class CancelacionForm(ControlBootstrapMixin, forms.Form):
    motivo = forms.CharField(
        label="Motivo de la cancelacion", max_length=255,
        widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()


class ReestructuracionForm(ControlBootstrapMixin, forms.Form):
    numero_cuotas = forms.IntegerField(label="Nuevo numero de cuotas", min_value=1)
    frecuencia_pago = forms.ChoiceField(
        label="Frecuencia", choices=FrecuenciaPago.choices)
    fecha_primer_pago = forms.DateField(
        label="Fecha del primer pago",
        widget=forms.DateInput(attrs={"type": "date"}))
    modalidad_interes = forms.ChoiceField(
        label="Modalidad de interes", choices=ModalidadInteres.choices, required=False)
    tasa_interes = forms.DecimalField(
        label="Tasa aplicada", max_digits=7, decimal_places=4, required=False,
        help_text="Deja vacio para conservar la tasa del credito original.")
    observaciones = forms.CharField(
        label="Observaciones", required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()
