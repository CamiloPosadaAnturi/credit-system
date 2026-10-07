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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        start, end = self.get_period()

        context["indicators"] = services.indicators(user, start=start, end=end)
        context["due_today"] = services.customers_due_today(user)
        context["past_due"] = services.customers_past_due(user)[:15]
        context["top_borrowers"] = services.top_borrowers(user, start=start, end=end)
        context["top_payers"] = services.top_payers(user, start=start, end=end)
        context["activity"] = services.recent_activity(user)
        if permissions.can(user, permissions.VIEW_REPORTS):
            context["collectors"] = services.collector_performance(
                user, start=start, end=end)
        # Passed as plain dicts: the template serializes them with json_script.
        context["payments_chart"] = services.scheduled_vs_collected(user)
        context["portfolio_chart"] = services.portfolio_composition(user)
        context["collection_series"] = services.collection_series(user)
        context["start"] = start.isoformat()
        context["end"] = end.isoformat()
        context["title"] = _("Dashboard")
        return context
