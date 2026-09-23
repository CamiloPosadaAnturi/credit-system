from django.urls import path

from apps.auditoria.views import AuditoriaListView

app_name = "auditoria"

urlpatterns = [
    path("", AuditoriaListView.as_view(), name="lista"),
]
