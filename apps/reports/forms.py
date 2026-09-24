from django import forms
from django.utils.translation import gettext_lazy as _

from apps.loans.models import LoanStatus
from apps.payments.models import PaymentMethod
from apps.users import permissions
from apps.users.models import Role, User


class ReportFilterForm(forms.Form):
    business = forms.ModelChoiceField(
        label=_("Business"), required=False, queryset=None, empty_label=_("All"),
        widget=forms.Select(attrs={"class": "form-select"}))
    start = forms.DateField(
        label=_("From"), required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    end = forms.DateField(
        label=_("To"), required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    status = forms.ChoiceField(
        label=_("Loan status"), required=False,
        choices=[("", _("All"))] + list(LoanStatus.choices),
        widget=forms.Select(attrs={"class": "form-select"}))
    collector = forms.ModelChoiceField(
        label=_("Collector"), required=False, queryset=None, empty_label=_("All"),
        widget=forms.Select(attrs={"class": "form-select"}))
    method = forms.ChoiceField(
        label=_("Payment method"), required=False,
        choices=[("", _("All"))] + list(PaymentMethod.choices),
        widget=forms.Select(attrs={"class": "form-select"}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        businesses = permissions.allowed_businesses(user) if user else None
        self.fields["business"].queryset = businesses
        self.fields["collector"].queryset = (
            User.objects.filter(role=Role.COLLECTOR, businesses__in=businesses).distinct()
            if businesses is not None else User.objects.collectors()
        )
