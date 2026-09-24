from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View

from apps.businesses.forms import BusinessFilterForm, BusinessForm
from apps.businesses.models import Business
from apps.businesses.services import business_summary
from apps.core.mixins import ActionRequiredMixin, AuditableMixin, SearchMixin
from apps.users import permissions


class BusinessBaseMixin(LoginRequiredMixin):
    model = Business

    def get_queryset(self):
        return permissions.allowed_businesses(self.request.user).select_related("manager")


class BusinessListView(BusinessBaseMixin, SearchMixin, ListView):
    template_name = "businesses/list.html"
    context_object_name = "businesses"
    paginate_by = 20
    search_fields = ["trade_name", "legal_name", "tax_id",
                     "manager__first_name", "manager__last_name",
                     "manager__username"]

    def get_queryset(self):
        queryset = super().get_queryset()
        form = BusinessFilterForm(self.request.GET or None)
        if form.is_valid():
            data = form.cleaned_data
            if data.get("is_active") == "1":
                queryset = queryset.filter(is_active=True)
            elif data.get("is_active") == "0":
                queryset = queryset.filter(is_active=False)
            if data.get("start"):
                queryset = queryset.filter(created_at__date__gte=data["start"])
            if data.get("end"):
                queryset = queryset.filter(created_at__date__lte=data["end"])
        self.filter_form = form
        return queryset.order_by("trade_name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        context["title"] = _("Businesses and branches")
        return context


class BusinessDetailView(BusinessBaseMixin, DetailView):
    template_name = "businesses/detail.html"
    context_object_name = "business"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["summary"] = business_summary(self.object)
        from apps.loans.models import Loan

        context["recent_loans"] = (
            Loan.objects.filter(business=self.object)
            .select_related("customer")
            .order_by("-created_at")[:10]
        )
        context["business_users"] = self.object.users.filter(is_active=True)
        return context


class BusinessCreateView(ActionRequiredMixin, AuditableMixin, CreateView):
    action = permissions.MANAGE_BUSINESSES
    model = Business
    form_class = BusinessForm
    template_name = "businesses/form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        # Whoever creates the business gets access to it, except the
        # super administrator who already sees the whole platform.
        if not self.request.user.is_superadmin:
            self.request.user.businesses.add(self.object)
        messages.success(
            self.request,
            _("Business '%(name)s' created successfully.") % {"name": self.object})
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("New business")
        return context


class BusinessUpdateView(ActionRequiredMixin, AuditableMixin, UpdateView):
    action = permissions.MANAGE_BUSINESSES
    model = Business
    form_class = BusinessForm
    template_name = "businesses/form.html"

    def get_queryset(self):
        return permissions.allowed_businesses(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, _("Business updated successfully."))
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("Edit %(name)s") % {"name": self.object}
        return context


class BusinessToggleActiveView(ActionRequiredMixin, View):
    """Safe deactivation: the financial history is never deleted."""

    action = permissions.MANAGE_BUSINESSES

    def post(self, request, pk):
        business = get_object_or_404(
            permissions.allowed_businesses(request.user), pk=pk)
        business.is_active = not business.is_active
        business.updated_by = request.user
        business.save(update_fields=["is_active", "updated_by", "updated_at"])
        if business.is_active:
            messages.success(
                request, _("Business '%(name)s' was activated.") % {"name": business})
        else:
            messages.success(
                request, _("Business '%(name)s' was deactivated.") % {"name": business})
        return redirect("businesses:detail", pk=business.pk)


class BusinessDashboardView(BusinessBaseMixin, DetailView):
    """Stand-alone dashboard for one business."""

    template_name = "businesses/dashboard.html"
    context_object_name = "business"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        start = self.request.GET.get("start") or None
        end = self.request.GET.get("end") or None
        context["summary"] = business_summary(self.object, start=start, end=end)
        context["start"] = start or ""
        context["end"] = end or ""
        return context


business_list = BusinessListView.as_view()
business_detail = BusinessDetailView.as_view()
business_create = BusinessCreateView.as_view()
business_update = BusinessUpdateView.as_view()
business_toggle_active = BusinessToggleActiveView.as_view()
business_dashboard = BusinessDashboardView.as_view()
