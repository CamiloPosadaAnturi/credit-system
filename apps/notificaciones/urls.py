from django.urls import path

from apps.notificaciones import views

app_name = "notificaciones"

urlpatterns = [
    path("", views.NotificacionListView.as_view(), name="lista"),
    path("leidas/", views.MarcarLeidasView.as_view(), name="marcar_leidas"),
    path("<int:pk>/leida/", views.MarcarLeidaView.as_view(), name="marcar_leida"),
]
