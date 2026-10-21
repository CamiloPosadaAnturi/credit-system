from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View

from apps.core.mixins import ActionRequiredMixin, AuditableMixin, SearchMixin
from apps.customers.forms import (
    CustomerFilterForm,
    CustomerForm,
    CustomerQuickForm,
)
from apps.customers.models import Customer, CustomerStatus
from apps.customers.services import customer_summary, payment_history
from apps.loans.forms import LoanForm
from apps.users import permissions


class CustomerBaseMixin(LoginRequiredMixin):
    model = Customer

    def get_queryset(self):
        queryset = permissions.filter_by_business(Customer.objects.all(), self.request.user)
        if getattr(self.request.user, "is_collector", False):
            # A collector only sees customers with loans assigned to them.
            queryset = permissions.filter_collector_portfolio(
                queryset, self.request.user, field="loans__collector").distinct()
        return queryset


class CustomerListView(SearchMixin, CustomerBaseMixin, ListView):
    template_name = "customers/list.html"
    context_object_name = "customers"
    paginate_by = 25
    search_fields = ["first_name", "last_name", "second_last_name", "phone", "code"]

    def get_queryset(self):
        queryset = super().get_queryset()
        self.filter_form = CustomerFilterForm(
            self.request.GET or None, user=self.request.user)
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data.get("status"):
                queryset = queryset.filter(status=data["status"])
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        if permissions.can(self.request.user, permissions.MANAGE_CUSTOMERS):
            context["quick_form"] = CustomerQuickForm()
        if permissions.can(self.request.user, permissions.CREATE_LOAN):
            context["loan_form"] = LoanForm.for_new_loan(user=self.request.user)
        context["title"] = _("Customers")
        return context


class CustomerDetailView(CustomerBaseMixin, DetailView):
    template_name = "customers/detail.html"
    context_object_name = "customer"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["summary"] = customer_summary(self.object)
        context["loans"] = self.object.loans.select_related("collector").order_by(
            "-application_date")
        context["payments"] = payment_history(self.object, limit=25)
        if permissions.can(self.request.user, permissions.CREATE_LOAN):
            context["loan_form"] = LoanForm.for_new_loan(self.object, user=self.request.user)
        return context


class CustomerFormMixin(AuditableMixin):
    form_class = CustomerForm
    template_name = "customers/form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class CustomerCreateView(ActionRequiredMixin, AuditableMixin, CreateView):
    """Quick registration: first name, last name and phone.

    The customer list opens it in a modal and submits it with ``fetch``: the
    view then answers JSON (the redirect, or the form re-rendered with its
    errors). Without JavaScript it works as a normal page.
    """

    action = permissions.MANAGE_CUSTOMERS
    model = Customer
    form_class = CustomerQuickForm
    template_name = "customers/quick_create.html"

    def is_ajax(self) -> bool:
        return self.request.headers.get("x-requested-with") == "XMLHttpRequest"

    def get_success_url(self) -> str:
        return reverse("customers:list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            _("Customer %(name)s registered.") % {"name": self.object.full_name})
        if self.is_ajax():
            return JsonResponse({"ok": True, "redirect": self.get_success_url()})
        return response

    def form_invalid(self, form):
        if self.is_ajax():
            html = render_to_string("customers/_quick_form.html", {"form": form},
                                    request=self.request)
            return JsonResponse({"ok": False, "html": html}, status=400)
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("New customer")
        return context


class CustomerUpdateView(ActionRequiredMixin, CustomerFormMixin, CustomerBaseMixin,
                         UpdateView):
    """Edit a customer.

    The customer list and detail pages open it in a modal: ``?modal=1``
    returns only the form, and the ``fetch`` submission answers JSON (the
    redirect, or the form re-rendered with its errors). Without JavaScript it
    works as a normal page.
    """

    action = permissions.MANAGE_CUSTOMERS

    def is_ajax(self) -> bool:
        return self.request.headers.get("x-requested-with") == "XMLHttpRequest"

    def get_template_names(self):
        if self.request.GET.get("modal"):
            return ["customers/_edit_form.html"]
        return [self.template_name]

    def get_success_url(self) -> str:
        next_url = self.request.POST.get("next") or self.request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={self.request.get_host()},
                require_https=self.request.is_secure()):
            return next_url
        return self.object.get_absolute_url()

    def form_valid(self, form):
        response = super().form_valid(form)
        if response.status_code in (301, 302):
            messages.success(self.request, _("Customer updated."))
            if self.is_ajax():
                return JsonResponse({"ok": True, "redirect": self.get_success_url()})
        return response

    def form_invalid(self, form):
        if self.is_ajax():
            html = render_to_string("customers/_edit_form.html",
                                    self.get_context_data(form=form), request=self.request)
            return JsonResponse({"ok": False, "html": html}, status=400)
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("Edit %(name)s") % {"name": self.object}
        return context


class CustomerChangeStatusView(ActionRequiredMixin, View):
    action = permissions.MANAGE_CUSTOMERS

    def post(self, request, pk):
        customer = get_object_or_404(
            permissions.filter_by_business(Customer.objects.all(), request.user), pk=pk)
        new_status = request.POST.get("status")
        if new_status not in CustomerStatus.values:
            messages.error(request, _("Invalid status."))
        else:
            customer.status = new_status
            customer.updated_by = request.user
            customer.save(update_fields=["status", "updated_by", "updated_at"])
            messages.success(
                request,
                _("The customer is now %(status)s.") % {
                    "status": customer.get_status_display()})
        return redirect(reverse("customers:detail", args=[customer.pk]))
