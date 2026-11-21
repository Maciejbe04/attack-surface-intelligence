from django.urls import path

from . import views

urlpatterns = [
    path("csrf/", views.csrf, name="auth-csrf"),
    path("me/", views.me, name="auth-me"),
    path("login/", views.login_view, name="auth-login"),
    path("mfa/verify/", views.mfa_verify, name="auth-mfa-verify"),
    path("logout/", views.logout_view, name="auth-logout"),
]
