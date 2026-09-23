from django.urls import path

from apps.cobranza import views

app_name = "cobranza"

urlpatterns = [
    path("", views.TableroCobranzaView.as_view(), name="tablero"),
    path("mi-cartera/", views.MiCarteraView.as_view(), name="mi_cartera"),
    path("gestiones/", views.GestionListView.as_view(), name="gestiones"),
    path("credito/<int:credito_id>/gestion/", views.RegistrarGestionView.as_view(),
         name="registrar_gestion"),
    path("actualizar-mora/", views.ActualizarMoraView.as_view(), name="actualizar_mora"),
]
