from django.urls import path

from apps.creditos import views

app_name = "creditos"

urlpatterns = [
    path("", views.CreditoListView.as_view(), name="lista"),
    path("nuevo/", views.CreditoCrearView.as_view(), name="crear"),
    path("simular/", views.simular_credito, name="simular"),
    path("<int:pk>/", views.CreditoDetailView.as_view(), name="detalle"),
    path("<int:pk>/editar/", views.CreditoEditarView.as_view(), name="editar"),
    path("<int:pk>/calendario/", views.CalendarioView.as_view(), name="calendario"),
    path("<int:pk>/aprobar/", views.AprobarCreditoView.as_view(), name="aprobar"),
    path("<int:pk>/desembolsar/", views.DesembolsarCreditoView.as_view(),
         name="desembolsar"),
    path("<int:pk>/cancelar/", views.CancelarCreditoView.as_view(), name="cancelar"),
    path("<int:pk>/reestructurar/", views.ReestructurarCreditoView.as_view(),
         name="reestructurar"),
]
