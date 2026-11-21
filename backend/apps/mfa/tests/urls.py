from django.urls import include, path

urlpatterns = [
    path("api/auth/mfa/", include("apps.mfa.urls")),
]
