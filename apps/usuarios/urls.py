from django.urls import path

from apps.usuarios import views

app_name = "usuarios"

urlpatterns = [
    path("entrar/", views.EntrarView.as_view(), name="login"),
    path("salir/", views.SalirView.as_view(), name="logout"),
    path("", views.UsuarioListView.as_view(), name="lista"),
    path("nuevo/", views.UsuarioCreateView.as_view(), name="crear"),
    path("perfil/", views.PerfilView.as_view(), name="perfil"),
    path("perfil/password/", views.cambiar_mi_password, name="mi_password"),
    path("<int:pk>/", views.UsuarioDetailView.as_view(), name="detalle"),
    path("<int:pk>/editar/", views.UsuarioUpdateView.as_view(), name="editar"),
    path("<int:pk>/password/", views.cambiar_password, name="password"),
]
