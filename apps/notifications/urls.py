from django.urls import path

from apps.notifications import views

app_name = "notifications"

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="list"),
    path("read-all/", views.MarkAllReadView.as_view(), name="mark_all_read"),
    path("<int:pk>/read/", views.MarkReadView.as_view(), name="mark_read"),
]
