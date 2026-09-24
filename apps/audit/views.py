from django.utils.translation import gettext as _
from django.views.generic import ListView

from apps.audit.models import AuditAction, AuditLog
from apps.core.mixins import ActionRequiredMixin, SearchMixin
from apps.users import permissions


class AuditLogListView(ActionRequiredMixin, SearchMixin, ListView):
    action = permissions.VIEW_AUDIT
    model = AuditLog
    template_name = "audit/list.html"
    context_object_name = "entries"
    paginate_by = 50
    search_fields = ["description", "model_name", "object_id",
                     "user__username", "user__first_name"]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("user", "business")
        if not self.request.user.is_superadmin:
            allowed = permissions.allowed_businesses(self.request.user)
            queryset = queryset.filter(business__in=allowed)
        action = self.request.GET.get("action")
        if action:
            queryset = queryset.filter(action=action)
        start = self.request.GET.get("start")
        end = self.request.GET.get("end")
        if start:
            queryset = queryset.filter(created_at__date__gte=start)
        if end:
            queryset = queryset.filter(created_at__date__lte=end)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["actions"] = AuditAction.choices
        context["selected_action"] = self.request.GET.get("action", "")
        context["start"] = self.request.GET.get("start", "")
        context["end"] = self.request.GET.get("end", "")
        context["title"] = _("Audit log")
        return context
