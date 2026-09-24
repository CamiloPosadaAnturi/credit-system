from django import forms
from django.utils.translation import gettext_lazy as _

from apps.businesses.models import Business
from apps.core.forms import BootstrapFormMixin
from apps.users.models import Role, User


class BusinessForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Business
        fields = [
            "trade_name", "legal_name", "tax_id", "phone", "email",
            "address", "city", "state", "manager", "is_active",
            "interest_mode", "interest_rate", "rate_period",
            "payment_frequency", "installment_count",
            "grace_days", "charges_late_fee", "late_fee_rate",
            "allows_early_payoff", "early_payoff_discount",
            "notes",
        ]
        widgets = {
            "address": forms.TextInput(),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    #: Field grouping used to render the form in sections.
    SECTIONS = [
        (_("General information"), ["trade_name", "legal_name", "tax_id", "phone",
                                    "email", "manager", "is_active"]),
        (_("Location"), ["address", "city", "state"]),
        (_("Interest configuration"), ["interest_mode", "interest_rate",
                                       "rate_period", "payment_frequency",
                                       "installment_count"]),
        (_("Late payment and payoff policy"), ["grace_days", "charges_late_fee",
                                               "late_fee_rate", "allows_early_payoff",
                                               "early_payoff_discount"]),
        (_("Other"), ["notes"]),
    ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["manager"].queryset = User.objects.active().exclude(role=Role.VIEWER)
        self.fields["tax_id"].required = False
        self.apply_widget_styles()

    def clean_tax_id(self):
        return (self.cleaned_data.get("tax_id") or "").upper().strip()

    def clean(self):
        data = super().clean()
        if data.get("charges_late_fee") and not data.get("late_fee_rate"):
            self.add_error(
                "late_fee_rate",
                _("If the business charges late fees you must set the daily rate."),
            )
        if not data.get("charges_late_fee"):
            data["late_fee_rate"] = 0
        return data


class BusinessFilterForm(forms.Form):
    q = forms.CharField(
        label=_("Search"), required=False,
        widget=forms.TextInput(attrs={"class": "form-control",
                                      "placeholder": _("Name, RFC or person in charge")}),
    )
    is_active = forms.ChoiceField(
        label=_("Status"), required=False,
        choices=[("", _("All")), ("1", _("Active")), ("0", _("Inactive"))],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    start = forms.DateField(
        label=_("Created from"), required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    end = forms.DateField(
        label=_("Created to"), required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
