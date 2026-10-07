"""Business settings.

The system operates a single business, so there is no list of businesses:
only one page to review and edit its data and commercial rules.
"""
from django.contrib import messages
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views.generic import TemplateView, UpdateView

from apps.businesses.forms import BusinessForm
from apps.businesses.models import Business
from apps.core.mixins import ActionRequiredMixin, AuditableMixin
from apps.users import permissions


class BusinessSettingsView(ActionRequiredMixin, TemplateView):
    action = permissions.MANAGE_BUSINESSES
    template_name = "businesses/detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["business"] = Business.objects.current()
        context["title"] = _("Settings")
        return context


class BusinessSettingsUpdateView(ActionRequiredMixin, AuditableMixin, UpdateView):
    action = permissions.MANAGE_BUSINESSES
    model = Business
    form_class = BusinessForm
    template_name = "businesses/form.html"
    success_url = reverse_lazy("businesses:settings")

    def get_object(self, queryset=None):
        return Business.objects.current()

    def form_valid(self, form):
        messages.success(self.request, _("Settings updated successfully."))
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("Edit settings")
        return context


business_settings = BusinessSettingsView.as_view()
business_settings_update = BusinessSettingsUpdateView.as_view()
