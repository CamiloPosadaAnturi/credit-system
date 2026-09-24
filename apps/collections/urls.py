from django.urls import path

from apps.collections import views

app_name = "collections"

urlpatterns = [
    path("", views.CollectionsBoardView.as_view(), name="board"),
    path("my-portfolio/", views.MyPortfolioView.as_view(), name="my_portfolio"),
    path("actions/", views.CollectionActionListView.as_view(), name="actions"),
    path("loan/<int:loan_id>/action/", views.LogCollectionActionView.as_view(),
         name="log_action"),
    path("refresh-past-due/", views.RefreshPastDueView.as_view(), name="refresh_past_due"),
]
