from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils.translation import gettext_lazy as _

from apps.core.forms import BootstrapFormMixin
from apps.users.models import Role, User


class LoginForm(BootstrapFormMixin, AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"placeholder": _("Username"), "autofocus": True}
        )
        self.fields["password"].widget.attrs.update({"placeholder": _("Password")})
        self.apply_widget_styles()


class UserForm(BootstrapFormMixin, forms.ModelForm):
    """Create and edit users, used by an administrator."""

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "phone",
                  "role", "is_active"]

    SECTIONS = [
        (_("Personal details"), ["first_name", "last_name", "email", "phone"]),
        (_("Access"), ["username", "role", "is_active"]),
    ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user is not None and not user.is_superadmin:
            # A business administrator cannot create super administrators.
            self.fields["role"].choices = [
                (value, label) for value, label in Role.choices
                if value != Role.SUPERADMIN
            ]
        self.apply_widget_styles()


class UserCreateForm(UserForm, UserCreationForm):
    class Meta(UserForm.Meta):
        fields = UserForm.Meta.fields

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("password1", "password2"):
            if name in self.fields:
                self.fields[name].widget.attrs["class"] = "form-control"


class SetPasswordForm(BootstrapFormMixin, forms.Form):
    password1 = forms.CharField(label=_("New password"), widget=forms.PasswordInput)
    password2 = forms.CharField(label=_("Confirm password"), widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_widget_styles()

    def clean(self):
        data = super().clean()
        if data.get("password1") != data.get("password2"):
            self.add_error("password2", _("The passwords do not match."))
        if len(data.get("password1") or "") < 8:
            self.add_error("password1",
                           _("The password must be at least 8 characters long."))
        return data


class ProfileForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_widget_styles()
