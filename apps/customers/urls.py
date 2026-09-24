from django.urls import path

from apps.customers import views

app_name = "customers"

urlpatterns = [
    path("", views.CustomerListView.as_view(), name="list"),
    path("new/", views.CustomerCreateView.as_view(), name="create"),
    path("<int:pk>/", views.CustomerDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.CustomerUpdateView.as_view(), name="update"),
    path("<int:pk>/status/", views.CustomerChangeStatusView.as_view(), name="status"),
]
