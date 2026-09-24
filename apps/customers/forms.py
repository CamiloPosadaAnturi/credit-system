from django import forms
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from apps.core.forms import BootstrapFormMixin
from apps.customers.models import Customer, CustomerStatus, PersonalReference
from apps.users import permissions
from apps.users.models import Role, User


class CustomerForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            "business", "first_name", "last_name", "second_last_name",
            "national_id", "tax_id", "birth_date",
            "phone", "alt_phone", "email",
            "address", "city", "state", "postal_code",
            "occupation", "collector", "status", "notes",
        ]
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    SECTIONS = [
        (_("Identification"), ["business", "first_name", "last_name",
                               "second_last_name", "birth_date", "occupation"]),
        (_("Documents (restricted access)"), ["national_id", "tax_id"]),
        (_("Contact"), ["phone", "alt_phone", "email"]),
        (_("Address"), ["address", "city", "state", "postal_code"]),
        (_("Operations"), ["collector", "status", "notes"]),
    ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user is not None:
            self.fields["business"].queryset = permissions.allowed_businesses(user).active()
            self.fields["collector"].queryset = User.objects.collectors().filter(
                businesses__in=permissions.allowed_businesses(user)
            ).distinct()
            if not permissions.can(user, permissions.VIEW_SENSITIVE_DATA):
                # Without the permission these fields are neither shown nor edited.
                self.fields.pop("national_id", None)
                self.fields.pop("tax_id", None)
        self.apply_widget_styles()

    def clean(self):
        data = super().clean()
        business = data.get("business")
        collector = data.get("collector")
        if business and collector and not collector.businesses.filter(
            pk=business.pk
        ).exists():
            self.add_error(
                "collector",
                _("The selected collector is not authorized for that business."),
            )
        return data


ReferenceFormSet = inlineformset_factory(
    Customer, PersonalReference,
    fields=["name", "relationship", "phone", "address"],
    extra=1, can_delete=True,
    widgets={
        "name": forms.TextInput(attrs={"class": "form-control"}),
        "relationship": forms.TextInput(attrs={"class": "form-control"}),
        "phone": forms.TextInput(attrs={"class": "form-control"}),
        "address": forms.TextInput(attrs={"class": "form-control"}),
    },
)


class CustomerFilterForm(forms.Form):
    q = forms.CharField(
        label=_("Search"), required=False,
        widget=forms.TextInput(attrs={"class": "form-control",
                                      "placeholder": _("Name, phone or code")}))
    business = forms.ModelChoiceField(
        label=_("Business"), required=False, queryset=None, empty_label=_("All"),
        widget=forms.Select(attrs={"class": "form-select"}))
    status = forms.ChoiceField(
        label=_("Status"), required=False,
        choices=[("", _("All"))] + list(CustomerStatus.choices),
        widget=forms.Select(attrs={"class": "form-select"}))
    collector = forms.ModelChoiceField(
        label=_("Collector"), required=False, queryset=None, empty_label=_("All"),
        widget=forms.Select(attrs={"class": "form-select"}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        businesses = permissions.allowed_businesses(user) if user else None
        self.fields["business"].queryset = businesses
        self.fields["collector"].queryset = (
            User.objects.filter(role=Role.COLLECTOR, businesses__in=businesses).distinct()
            if businesses is not None
            else User.objects.collectors()
        )
