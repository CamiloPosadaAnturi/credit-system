from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core.mixins import ActionRequiredMixin, SearchMixin
from apps.users import permissions
from apps.users.forms import (
    LoginForm,
    ProfileForm,
    SetPasswordForm,
    UserCreateForm,
    UserForm,
)
from apps.users.models import Role, User


class SignInView(LoginView):
    template_name = "users/login.html"
    form_class = LoginForm
    redirect_authenticated_user = True


class SignOutView(LogoutView):
    pass


class UserListView(ActionRequiredMixin, SearchMixin, ListView):
    action = permissions.MANAGE_USERS
    model = User
    template_name = "users/list.html"
    context_object_name = "users"
    paginate_by = 20
    search_fields = ["username", "first_name", "last_name", "email"]

    def get_queryset(self):
        queryset = super().get_queryset().prefetch_related("businesses")
        if not self.request.user.is_superadmin:
            queryset = queryset.filter(
                Q(businesses__in=permissions.allowed_businesses(self.request.user))
            ).distinct()
        role = self.request.GET.get("role")
        if role:
            queryset = queryset.filter(role=role)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["roles"] = Role.choices
        context["selected_role"] = self.request.GET.get("role", "")
        context["title"] = _("Users")
        return context


class UserCreateView(ActionRequiredMixin, CreateView):
    action = permissions.MANAGE_USERS
    model = User
    form_class = UserCreateForm
    template_name = "users/form.html"
    success_url = reverse_lazy("users:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, _("User created successfully."))
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("New user")
        return context


class UserUpdateView(ActionRequiredMixin, UpdateView):
    action = permissions.MANAGE_USERS
    model = User
    form_class = UserForm
    template_name = "users/form.html"
    success_url = reverse_lazy("users:list")

    def get_queryset(self):
        queryset = User.objects.all()
        if not self.request.user.is_superadmin:
            queryset = queryset.filter(
                businesses__in=permissions.allowed_businesses(self.request.user)
            ).distinct()
        return queryset

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, _("User updated."))
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("Edit %(name)s") % {"name": self.object}
        return context


class UserDetailView(ActionRequiredMixin, DetailView):
    action = permissions.MANAGE_USERS
    model = User
    template_name = "users/detail.html"
    context_object_name = "profile_user"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.customers.models import Customer
        from apps.loans.models import Loan

        context["assigned_customers"] = Customer.objects.filter(
            collector=self.object).count()
        context["assigned_loans"] = Loan.objects.filter(collector=self.object).count()
        return context


def set_user_password(request, pk):
    permissions.require(request.user, permissions.MANAGE_USERS)
    user = get_object_or_404(User, pk=pk)
    if not request.user.is_superadmin:
        allowed = permissions.allowed_businesses(request.user)
        if not user.businesses.filter(pk__in=allowed).exists():
            raise PermissionDenied(_("You cannot modify this user."))
    form = SetPasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user.set_password(form.cleaned_data["password1"])
        user.save(update_fields=["password"])
        messages.success(
            request, _("Password for %(name)s updated.") % {"name": user})
        return redirect("users:detail", pk=user.pk)
    return render(request, "users/set_password.html",
                  {"form": form, "profile_user": user})


class ProfileView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = ProfileForm
    template_name = "users/profile.html"
    success_url = reverse_lazy("users:profile")

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, _("Profile updated."))
        return super().form_valid(form)


def change_own_password(request):
    from django.contrib.auth.forms import PasswordChangeForm

    form = PasswordChangeForm(request.user, request.POST or None)
    for field in form.fields.values():
        field.widget.attrs.setdefault("class", "form-control")
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, _("Your password was updated."))
        return redirect("users:profile")
    return render(request, "users/set_password.html",
                  {"form": form, "profile_user": request.user, "own": True})
