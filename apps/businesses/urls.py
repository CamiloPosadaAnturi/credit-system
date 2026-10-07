from django.urls import path

from apps.businesses import views

app_name = "businesses"

urlpatterns = [
    path("", views.business_settings, name="settings"),
    path("edit/", views.business_settings_update, name="settings_edit"),
]
