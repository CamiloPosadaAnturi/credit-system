from django import forms
from django.utils.translation import gettext_lazy as _

from apps.businesses.models import Business
from apps.core.forms import BootstrapFormMixin
from apps.customers.models import Customer, CustomerStatus


class CustomerForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            "first_name", "last_name", "second_last_name", "phone", "status", "notes",
        ]
        widgets = {
            "phone": forms.TextInput(attrs={"type": "tel", "inputmode": "tel"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    SECTIONS = [
        (_("Identification"), ["first_name", "last_name", "second_last_name", "phone"]),
        (_("Operations"), ["status", "notes"]),
    ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if not self.instance.business_id:
            # Single-business mode: every customer belongs to the one business.
            self.instance.business = Business.objects.current()
        self.apply_widget_styles()

    def full_clean(self):
        super().full_clean()
        # Highlight the fields with errors (Bootstrap ``is-invalid``).
        for name in self.errors:
            if name in self.fields:
                widget = self.fields[name].widget
                widget.attrs["class"] = f"{widget.attrs.get('class', '')} is-invalid".strip()


class CustomerQuickForm(BootstrapFormMixin, forms.ModelForm):
    """Register a customer with the minimum data: name, last name and phone.

    The rest of the profile (second last name, notes) is
    completed later from the edit modal.
    """

    class Meta:
        model = Customer
        fields = ["first_name", "last_name", "phone"]
        labels = {"last_name": _("Last name"), "phone": _("Phone")}
        widgets = {
            "first_name": forms.TextInput(attrs={"autocomplete": "off"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "off"}),
            "phone": forms.TextInput(attrs={"type": "tel", "inputmode": "tel",
                                            "autocomplete": "off"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.business_id:
            # Single-business mode: every customer belongs to the one business.
            self.instance.business = Business.objects.current()
        self.apply_widget_styles()

    def full_clean(self):
        super().full_clean()
        # Highlight the fields with errors (Bootstrap ``is-invalid``).
        for name in self.errors:
            if name in self.fields:
                widget = self.fields[name].widget
                widget.attrs["class"] = f"{widget.attrs.get('class', '')} is-invalid".strip()


class CustomerFilterForm(forms.Form):
    q = forms.CharField(
        label=_("Search"), required=False,
        widget=forms.TextInput(attrs={"class": "form-control",
                                      "placeholder": _("Name, phone or code")}))
    status = forms.ChoiceField(
        label=_("Status"), required=False,
        choices=[("", _("All"))] + list(CustomerStatus.choices),
        widget=forms.Select(attrs={"class": "form-select"}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
