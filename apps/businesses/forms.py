from django import forms
from django.utils.translation import gettext_lazy as _

from apps.businesses.models import Business
from apps.core.choices import PaymentFrequency
from apps.core.forms import BootstrapFormMixin
from apps.users.models import Role, User


class BusinessForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Business
        fields = [
            "trade_name", "legal_name", "tax_id", "phone", "email",
            "address", "city", "state", "manager",
            "interest_rate", "payment_frequency", "installment_count",
            "grace_days", "allows_early_payoff", "early_payoff_discount",
            "notes",
        ]
        widgets = {
            "address": forms.TextInput(),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    #: Field grouping used to render the form in sections.
    SECTIONS = [
        (_("General information"), ["trade_name", "legal_name", "tax_id", "phone",
                                    "email", "manager"]),
        (_("Location"), ["address", "city", "state"]),
        (_("Interest configuration"), ["interest_rate", "payment_frequency",
                                       "installment_count"]),
        (_("Late payment and payoff policy"), ["grace_days", "allows_early_payoff",
                                               "early_payoff_discount"]),
        (_("Other"), ["notes"]),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["manager"].queryset = User.objects.active().exclude(role=Role.VIEWER)
        self.fields["tax_id"].required = False
        # Loans charge rate x principal and use the standard frequencies.
        self.fields["interest_rate"].help_text = _(
            "Interest = rate x principal. 0.40 = 40% (400 MXN per 1,000 MXN lent).")
        self.fields["payment_frequency"].choices = [
            (value, label) for value, label in PaymentFrequency.choices
            if value != PaymentFrequency.CUSTOM
        ]
        self.apply_widget_styles()

    def clean_tax_id(self):
        return (self.cleaned_data.get("tax_id") or "").upper().strip()
