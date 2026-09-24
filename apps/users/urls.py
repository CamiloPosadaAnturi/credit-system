from django.urls import path

from apps.users import views

app_name = "users"

urlpatterns = [
    path("sign-in/", views.SignInView.as_view(), name="login"),
    path("sign-out/", views.SignOutView.as_view(), name="logout"),
    path("", views.UserListView.as_view(), name="list"),
    path("new/", views.UserCreateView.as_view(), name="create"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("profile/password/", views.change_own_password, name="own_password"),
    path("<int:pk>/", views.UserDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.UserUpdateView.as_view(), name="update"),
    path("<int:pk>/password/", views.set_user_password, name="password"),
]
