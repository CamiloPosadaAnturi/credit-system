from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.choices import InterestMode, PaymentFrequency
from apps.core.forms import BootstrapFormMixin, DateInput
from apps.customers.models import Customer
from apps.loans.models import Loan, LoanStatus
from apps.users.models import Role, User

#: Frequencies offered when creating a loan (the custom "every N days" one
#: is not used by the business).
LOAN_FREQUENCIES = [
    (value, label) for value, label in PaymentFrequency.choices
    if value != PaymentFrequency.CUSTOM
]


class LoanForm(BootstrapFormMixin, forms.ModelForm):
    """Loan terms.

    Only the principal and the schedule are captured. The interest is always
    the business rate (Settings) x principal, and the collector is the one
    assigned to the customer. Interest, total and schedule are computed by
    the service layer.
    """

    class Meta:
        model = Loan
        fields = [
            "customer", "principal", "payment_frequency", "installment_count",
            "first_payment_date", "application_date", "notes",
        ]
        widgets = {
            "application_date": DateInput(),
            "first_payment_date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 2}),
            "principal": forms.NumberInput(attrs={"step": "0.01", "min": "0.01",
                                                  "inputmode": "decimal"}),
            "installment_count": forms.NumberInput(attrs={"min": "1"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["customer"].queryset = Customer.objects.active()
        self.fields["customer"].empty_label = _("Select a customer")
        self.fields["payment_frequency"].choices = LOAN_FREQUENCIES
        from apps.businesses.models import Business

        #: Shown in the preview: the interest is always this rate x principal.
        self.rate_percentage = Business.objects.current().rate_percentage
        self.apply_widget_styles()

    @classmethod
    def for_new_loan(cls, customer=None, user=None):
        """Unbound form with the defaults of the business configuration."""
        from apps.businesses.models import Business
        from apps.core.dates import today_local

        business = Business.objects.current()
        initial = {
            "application_date": today_local(),
            "first_payment_date": today_local(),
            "payment_frequency": business.payment_frequency
            if business.payment_frequency != PaymentFrequency.CUSTOM
            else PaymentFrequency.WEEKLY,
            "installment_count": business.installment_count,
        }
        if customer is not None:
            initial["customer"] = customer.pk
        return cls(initial=initial, user=user)

    def full_clean(self):
        super().full_clean()
        # Highlight the fields with errors (Bootstrap ``is-invalid``).
        for name in self.errors:
            if name in self.fields:
                widget = self.fields[name].widget
                widget.attrs["class"] = f"{widget.attrs.get('class', '')} is-invalid".strip()

    def clean(self):
        data = super().clean()
        principal = data.get("principal")
        installments = data.get("installment_count")
        if principal is not None and principal <= 0:
            self.add_error("principal", _("The principal must be greater than zero."))
        if installments is not None and installments < 1:
            self.add_error("installment_count", _("There must be at least one installment."))
        return data


class LoanFilterForm(forms.Form):
    q = forms.CharField(
        label=_("Search"), required=False,
        widget=forms.TextInput(attrs={"class": "form-control",
                                      "placeholder": _("Reference or customer")}))
    status = forms.ChoiceField(
        label=_("Status"), required=False,
        choices=[("", _("All"))] + list(LoanStatus.choices),
        widget=forms.Select(attrs={"class": "form-select"}))
    collector = forms.ModelChoiceField(
        label=_("Collector"), required=False, queryset=None, empty_label=_("All"),
        widget=forms.Select(attrs={"class": "form-select"}))
    start = forms.DateField(
        label=_("Disbursed from"), required=False,
        widget=DateInput(attrs={"class": "form-control"}))
    end = forms.DateField(
        label=_("Disbursed to"), required=False,
        widget=DateInput(attrs={"class": "form-control"}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["collector"].queryset = User.objects.filter(role=Role.COLLECTOR)


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
        widget=DateInput())
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
