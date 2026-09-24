from django.urls import path

from apps.payments import views

app_name = "payments"

urlpatterns = [
    path("", views.PaymentListView.as_view(), name="list"),
    path("loan/<int:loan_id>/register/", views.RegisterPaymentView.as_view(),
         name="register"),
    path("loan/<int:loan_id>/payoff/", views.EarlyPayoffView.as_view(), name="payoff"),
    path("<int:pk>/", views.PaymentDetailView.as_view(), name="detail"),
    path("<int:pk>/reverse/", views.ReversePaymentView.as_view(), name="reverse"),
]
