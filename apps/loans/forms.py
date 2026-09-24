from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.choices import InterestMode, PaymentFrequency
from apps.core.forms import BootstrapFormMixin
from apps.customers.models import Customer
from apps.loans.models import Loan, LoanStatus
from apps.users import permissions
from apps.users.models import Role, User


class LoanForm(BootstrapFormMixin, forms.ModelForm):
    """Loan terms.

    Interest, total and schedule are NOT captured: the service layer
    computes them from these terms.
    """

    class Meta:
        model = Loan
        fields = [
            "business", "customer", "collector", "application_date", "principal",
            "interest_mode", "interest_rate", "rate_period",
            "payment_frequency", "custom_days", "installment_count",
            "first_payment_date", "notes", "contract",
        ]
        widgets = {
            "application_date": forms.DateInput(attrs={"type": "date"}),
            "first_payment_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "principal": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "interest_rate": forms.NumberInput(attrs={"step": "0.0001", "min": "0"}),
        }

    SECTIONS = [
        (_("Application"), ["business", "customer", "collector", "application_date"]),
        (_("Financial terms"), ["principal", "interest_mode", "interest_rate",
                                "rate_period"]),
        (_("Schedule"), ["payment_frequency", "installment_count", "custom_days",
                         "first_payment_date"]),
        (_("Documents"), ["notes", "contract"]),
    ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        businesses = permissions.allowed_businesses(user) if user else None
        if businesses is not None:
            self.fields["business"].queryset = businesses.active()
            self.fields["customer"].queryset = (
                Customer.objects.filter(business__in=businesses).active()
                .select_related("business")
            )
            self.fields["collector"].queryset = (
                User.objects.filter(role=Role.COLLECTOR, businesses__in=businesses)
                .distinct()
            )
        self.fields["custom_days"].help_text = _("Only for the custom frequency.")
        self.fields["interest_rate"].help_text = _(
            "Ratio. 0.40 = 40% (400 MXN per 1,000 MXN lent)."
        )
        self.apply_widget_styles()

    def clean(self):
        data = super().clean()
        business = data.get("business")
        customer = data.get("customer")
        frequency = data.get("payment_frequency")
        custom_days = data.get("custom_days")
        principal = data.get("principal")
        installments = data.get("installment_count")

        if business and customer and customer.business_id != business.pk:
            self.add_error("customer",
                           _("The customer does not belong to the selected business."))
        if frequency == PaymentFrequency.CUSTOM and not custom_days:
            self.add_error("custom_days",
                           _("State how many days apart the installments fall."))
        if principal is not None and principal <= 0:
            self.add_error("principal", _("The principal must be greater than zero."))
        if installments is not None and installments < 1:
            self.add_error("installment_count", _("There must be at least one installment."))
        if data.get("interest_mode") != InterestMode.NO_INTEREST:
            if data.get("interest_rate") in (None, ""):
                self.add_error("interest_rate", _("State the applied rate."))
        return data


class LoanFilterForm(forms.Form):
    q = forms.CharField(
        label=_("Search"), required=False,
        widget=forms.TextInput(attrs={"class": "form-control",
                                      "placeholder": _("Reference or customer")}))
    business = forms.ModelChoiceField(
        label=_("Business"), required=False, queryset=None, empty_label=_("All"),
        widget=forms.Select(attrs={"class": "form-select"}))
    status = forms.ChoiceField(
        label=_("Status"), required=False,
        choices=[("", _("All"))] + list(LoanStatus.choices),
        widget=forms.Select(attrs={"class": "form-select"}))
    collector = forms.ModelChoiceField(
        label=_("Collector"), required=False, queryset=None, empty_label=_("All"),
        widget=forms.Select(attrs={"class": "form-select"}))
    start = forms.DateField(
        label=_("Disbursed from"), required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    end = forms.DateField(
        label=_("Disbursed to"), required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        businesses = permissions.allowed_businesses(user) if user else None
        self.fields["business"].queryset = businesses
        self.fields["collector"].queryset = (
            User.objects.filter(role=Role.COLLECTOR, businesses__in=businesses).distinct()
            if businesses is not None else User.objects.collectors()
        )


class CancellationForm(BootstrapFormMixin, forms.Form):
    reason = forms.CharField(
        label=_("Cancellation reason"), max_length=255,
        widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_widget_styles()


class RestructuringForm(BootstrapFormMixin, forms.Form):
    installment_count = forms.IntegerField(label=_("New number of installments"),
                                           min_value=1)
    payment_frequency = forms.ChoiceField(
        label=_("Frequency"), choices=PaymentFrequency.choices)
    first_payment_date = forms.DateField(
        label=_("First payment date"),
        widget=forms.DateInput(attrs={"type": "date"}))
    interest_mode = forms.ChoiceField(
        label=_("Interest mode"), choices=InterestMode.choices, required=False)
    interest_rate = forms.DecimalField(
        label=_("Applied rate"), max_digits=7, decimal_places=4, required=False,
        help_text=_("Leave empty to keep the rate of the original loan."))
    notes = forms.CharField(
        label=_("Notes"), required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_widget_styles()
