"""MFA routes. Intentionally NOT included in config/urls.py yet.

To enable, add to config/urls.py::

    path("api/auth/mfa/", include("apps.mfa.urls")),

and set ``MFA_ENABLED=1``. Details: docs/mfa-backend.md.
"""

from django.urls import path

from . import views

app_name = "mfa"

urlpatterns = [
    path("status/", views.mfa_status, name="status"),
    path("enroll/", views.enroll_start, name="enroll-start"),
    path("enroll/confirm/", views.enroll_confirm, name="enroll-confirm"),
    path("disable/", views.disable, name="disable"),
    path("recovery-codes/", views.regenerate_recovery_codes, name="recovery-codes"),
    path("challenge/", views.complete_login_challenge, name="challenge"),
]
