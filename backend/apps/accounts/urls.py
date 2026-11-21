from django.urls import path

from . import views

urlpatterns = [
    path("csrf/", views.csrf, name="auth-csrf"),
    path("me/", views.me, name="auth-me"),
    path("login/", views.login_view, name="auth-login"),
    path("mfa/verify/", views.mfa_verify, name="auth-mfa-verify"),
    path("logout/", views.logout_view, name="auth-logout"),
    path("users/", views.UserListCreateView.as_view(), name="user-list"),
    path("users/<int:user_id>/", views.UserDetailView.as_view(), name="user-detail"),
]
