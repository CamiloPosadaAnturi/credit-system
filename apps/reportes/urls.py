from django.urls import path

from apps.reportes import views

app_name = "reportes"

urlpatterns = [
    path("", views.CatalogoReportesView.as_view(), name="catalogo"),
    path("<str:clave>/", views.ReporteView.as_view(), name="detalle"),
]
