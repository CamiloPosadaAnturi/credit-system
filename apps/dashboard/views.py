import datetime as dt

from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.translation import gettext as _
from django.views.generic import TemplateView

from apps.core.dates import today_local
from apps.dashboard import services
from apps.users import permissions


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"

    def get_period(self):
        today = today_local()
        start = self.request.GET.get("start") or today.replace(day=1).isoformat()
        end = self.request.GET.get("end") or today.isoformat()
        try:
            return (dt.date.fromisoformat(start), dt.date.fromisoformat(end))
        except ValueError:
            return (today.replace(day=1), today)

    def get_business(self):
        value = self.request.GET.get("business")
        if not value:
            return None
        return permissions.allowed_businesses(self.request.user).filter(pk=value).first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        start, end = self.get_period()
        business = self.get_business()

        context["indicators"] = services.indicators(user, business, start, end)
        context["due_today"] = services.customers_due_today(user, business)
        context["past_due"] = services.customers_past_due(user, business)[:15]
        context["top_borrowers"] = services.top_borrowers(user, business, start, end)
        context["top_payers"] = services.top_payers(user, business, start, end)
        context["activity"] = services.recent_activity(user, business)
        if permissions.can(user, permissions.VIEW_REPORTS):
            context["collectors"] = services.collector_performance(
                user, business, start, end)
        # Passed as plain dicts: the template serializes them with json_script.
        context["payments_chart"] = services.scheduled_vs_collected(user, business)
        context["portfolio_chart"] = services.portfolio_composition(user, business)
        context["collection_series"] = services.collection_series(user, business)
        context["start"] = start.isoformat()
        context["end"] = end.isoformat()
        context["selected_business"] = business
        context["title"] = _("Dashboard")
        return context
