from django.urls import path

from apps.pagos import views

app_name = "pagos"

urlpatterns = [
    path("", views.PagoListView.as_view(), name="lista"),
    path("credito/<int:credito_id>/registrar/", views.RegistrarPagoView.as_view(),
         name="registrar"),
    path("credito/<int:credito_id>/liquidar/", views.LiquidarAnticipadoView.as_view(),
         name="liquidar"),
    path("<int:pk>/", views.PagoDetailView.as_view(), name="detalle"),
    path("<int:pk>/reversar/", views.ReversarPagoView.as_view(), name="reversar"),
]
