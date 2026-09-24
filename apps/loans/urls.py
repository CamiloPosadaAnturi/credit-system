from django.urls import path

from apps.loans import views

app_name = "loans"

urlpatterns = [
    path("", views.LoanListView.as_view(), name="list"),
    path("new/", views.LoanCreateView.as_view(), name="create"),
    path("simulate/", views.simulate_loan, name="simulate"),
    path("<int:pk>/", views.LoanDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.LoanUpdateView.as_view(), name="update"),
    path("<int:pk>/schedule/", views.ScheduleView.as_view(), name="schedule"),
    path("<int:pk>/approve/", views.ApproveLoanView.as_view(), name="approve"),
    path("<int:pk>/disburse/", views.DisburseLoanView.as_view(), name="disburse"),
    path("<int:pk>/cancel/", views.CancelLoanView.as_view(), name="cancel"),
    path("<int:pk>/restructure/", views.RestructureLoanView.as_view(), name="restructure"),
]
