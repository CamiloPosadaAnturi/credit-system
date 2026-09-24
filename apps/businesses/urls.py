from django.urls import path

from apps.businesses import views

app_name = "businesses"

urlpatterns = [
    path("", views.business_list, name="list"),
    path("new/", views.business_create, name="create"),
    path("<int:pk>/", views.business_detail, name="detail"),
    path("<int:pk>/edit/", views.business_update, name="update"),
    path("<int:pk>/toggle-active/", views.business_toggle_active, name="toggle_active"),
    path("<int:pk>/dashboard/", views.business_dashboard, name="dashboard"),
]
