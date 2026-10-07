from django import forms
from django.utils.translation import gettext_lazy as _

from apps.collections.models import ActionOutcome, ActionType, CollectionAction
from apps.core.forms import BootstrapFormMixin
from apps.users.models import Role, User


class CollectionActionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = CollectionAction
        fields = ["action_type", "outcome", "promised_amount", "promise_date",
                  "next_contact_date", "notes"]
        widgets = {
            "promise_date": forms.DateInput(attrs={"type": "date"}),
            "next_contact_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "promised_amount": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_widget_styles()

    def clean(self):
        data = super().clean()
        action_type = data.get("action_type")
        if action_type in (ActionType.PROMISE, ActionType.AGREEMENT):
            if not data.get("promise_date"):
                self.add_error("promise_date",
                               _("State the date the customer committed to."))
            if not data.get("promised_amount"):
                self.add_error("promised_amount", _("State the promised amount."))
        return data


class CollectionsFilterForm(forms.Form):
    collector = forms.ModelChoiceField(
        label=_("Collector"), required=False, queryset=None, empty_label=_("All"),
        widget=forms.Select(attrs={"class": "form-select"}))
    start = forms.DateField(
        label=_("From"), required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    end = forms.DateField(
        label=_("To"), required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    min_days_past_due = forms.IntegerField(
        label=_("Minimum days past due"), required=False, min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "0"}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["collector"].queryset = User.objects.filter(role=Role.COLLECTOR)


class CollectionActionFilterForm(CollectionsFilterForm):
    action_type = forms.ChoiceField(
        label=_("Type"), required=False,
        choices=[("", _("All"))] + list(ActionType.choices),
        widget=forms.Select(attrs={"class": "form-select"}))
    outcome = forms.ChoiceField(
        label=_("Outcome"), required=False,
        choices=[("", _("All"))] + list(ActionOutcome.choices),
        widget=forms.Select(attrs={"class": "form-select"}))
