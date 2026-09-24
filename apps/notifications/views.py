from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from django.views.generic import ListView, View

from apps.notifications.models import Notification
from apps.notifications.services import notifications_for


class NotificationListView(LoginRequiredMixin, ListView):
    template_name = "notifications/list.html"
    context_object_name = "notifications"
    paginate_by = 30

    def get_queryset(self):
        return notifications_for(self.request.user, unread_only=False).select_related(
            "business")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("Notifications")
        return context


class MarkAllReadView(LoginRequiredMixin, View):
    def post(self, request):
        notifications_for(request.user).update(is_read=True)
        return redirect("notifications:list")


class MarkReadView(LoginRequiredMixin, View):
    def post(self, request, pk):
        Notification.objects.filter(
            pk=pk, business__in=request.user.allowed_businesses()
        ).update(is_read=True)
        return redirect(request.META.get("HTTP_REFERER", "notifications:list"))
