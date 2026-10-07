from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import BootstrapFormMixin
from apps.payments.models import PaymentMethod, PaymentStatus
from apps.users.models import Role, User


class PaymentForm(BootstrapFormMixin, forms.Form):
    """Capture a payment. The service layer computes and allocates it."""

    amount = forms.DecimalField(
        label=_("Amount received (MXN)"), max_digits=12, decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={"step": "0.01", "autofocus": True}))
    method = forms.ChoiceField(label=_("Payment method"), choices=PaymentMethod.choices)
    paid_at = forms.DateTimeField(
        label=_("Payment date and time"), required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        help_text=_("Leave empty to use the current date and time."))
    external_reference = forms.CharField(label=_("Reference"), max_length=80,
                                         required=False)
    notes = forms.CharField(
        label=_("Notes"), required=False, widget=forms.Textarea(attrs={"rows": 2}))
    allow_overpayment = forms.BooleanField(
        label=_("I authorize an amount larger than the balance (overpayment)"),
        required=False)
    confirm_duplicate = forms.BooleanField(
        label=_("I confirm this is not a duplicate payment"), required=False)
    idempotency_key = forms.CharField(widget=forms.HiddenInput, required=False)

    def __init__(self, *args, loan=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.loan = loan
        self.apply_widget_styles()

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError(_("The amount must be greater than zero."))
        return amount


class ReversalForm(BootstrapFormMixin, forms.Form):
    reason = forms.CharField(
        label=_("Reversal reason"), max_length=255,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("It is recorded in the audit log. The original payment is kept."))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_widget_styles()


class PayoffForm(BootstrapFormMixin, forms.Form):
    method = forms.ChoiceField(label=_("Payment method"), choices=PaymentMethod.choices)
    external_reference = forms.CharField(label=_("Reference"), max_length=80,
                                         required=False)
    notes = forms.CharField(
        label=_("Notes"), required=False, widget=forms.Textarea(attrs={"rows": 2}))
    idempotency_key = forms.CharField(widget=forms.HiddenInput, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_widget_styles()


class PaymentFilterForm(forms.Form):
    q = forms.CharField(
        label=_("Search"), required=False,
        widget=forms.TextInput(attrs={"class": "form-control",
                                      "placeholder": _("Reference, customer or note")}))
    method = forms.ChoiceField(
        label=_("Method"), required=False,
        choices=[("", _("All"))] + list(PaymentMethod.choices),
        widget=forms.Select(attrs={"class": "form-select"}))
    status = forms.ChoiceField(
        label=_("Status"), required=False,
        choices=[("", _("All"))] + list(PaymentStatus.choices),
        widget=forms.Select(attrs={"class": "form-select"}))
    collector = forms.ModelChoiceField(
        label=_("Collector"), required=False, queryset=None, empty_label=_("All"),
        widget=forms.Select(attrs={"class": "form-select"}))
    start = forms.DateField(
        label=_("From"), required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    end = forms.DateField(
        label=_("To"), required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["collector"].queryset = User.objects.filter(role=Role.COLLECTOR)
