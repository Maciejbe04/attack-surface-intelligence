"""REST endpoints for MFA. Not routed yet: see docs/mfa-backend.md to enable.

All responses that carry a secret (TOTP secret, recovery codes) are marked
``Cache-Control: no-store`` so browsers and proxies do not keep them.
"""

from __future__ import annotations

import time

from django.contrib.auth import login
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from . import challenge, services
# Session key set after a successful second factor; the admin guard requires it.
from .admin_guard import SESSION_MFA_VERIFIED_AT

_ERROR_STATUS = {
    services.NotEnrolled: status.HTTP_409_CONFLICT,
    services.AlreadyEnrolled: status.HTTP_409_CONFLICT,
    services.EnrollmentExpired: status.HTTP_410_GONE,
    services.InvalidCode: status.HTTP_400_BAD_REQUEST,
    services.LockedOut: status.HTTP_429_TOO_MANY_REQUESTS,
    challenge.ChallengeInvalid: status.HTTP_401_UNAUTHORIZED,
}



def _no_store(response: Response) -> Response:
    response["Cache-Control"] = "no-store, max-age=0"
    response["Pragma"] = "no-cache"
    return response


def _error(exc: services.MfaError) -> Response:
    http_status = _ERROR_STATUS.get(type(exc), status.HTTP_400_BAD_REQUEST)
    return _no_store(Response({"detail": str(exc), "code": exc.code}, status=http_status))


def _disabled() -> Response:
    return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)


def _password_confirmed(request: Request) -> bool:
    """Sensitive changes need the current password, so a stolen session is not enough."""
    password = request.data.get("password")
    if not isinstance(password, str) or not password:
        return False
    if request.user.check_password(password):
        return True
    services.record_failed_attempt(request.user)
    return False


def _password_error() -> Response:
    return _no_store(
        Response(
            {"detail": "Password confirmation failed.", "code": "password_required"},
            status=status.HTTP_403_FORBIDDEN,
        )
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mfa_status(request: Request) -> Response:
    if not services.is_feature_enabled():
        return _disabled()
    user = request.user
    return _no_store(
        Response(
            {
                "enrolled": services.user_has_mfa(user),
                "pending_enrollment": services.get_pending_enrollment(user) is not None,
                "recovery_codes_remaining": services.remaining_recovery_codes(user),
                "locked_out": services.is_locked_out(user),
            }
        )
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def enroll_start(request: Request) -> Response:
    if not services.is_feature_enabled():
        return _disabled()
    if services.is_locked_out(request.user):
        return _error(services.LockedOut("Too many failed attempts. Try again later."))
    if not _password_confirmed(request):
        return _password_error()
    try:
        enrollment = services.start_enrollment(request.user)
    except services.MfaError as exc:
        return _error(exc)
    return _no_store(
        Response(
            {
                "secret": enrollment.secret,
                "otpauth_uri": enrollment.otpauth_uri,
                "expires_in": enrollment.expires_in_seconds,
            },
            status=status.HTTP_201_CREATED,
        )
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def enroll_confirm(request: Request) -> Response:
    if not services.is_feature_enabled():
        return _disabled()
    try:
        codes = services.confirm_enrollment(request.user, request.data.get("code"))
    except services.MfaError as exc:
        return _error(exc)
    request.session[SESSION_MFA_VERIFIED_AT] = int(time.time())
    return _no_store(Response({"recovery_codes": codes}))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def disable(request: Request) -> Response:
    if not services.is_feature_enabled():
        return _disabled()
    if services.is_locked_out(request.user):
        return _error(services.LockedOut("Too many failed attempts. Try again later."))
    if not _password_confirmed(request):
        return _password_error()
    try:
        services.disable(request.user, request.data.get("code"))
    except services.MfaError as exc:
        return _error(exc)
    request.session.pop(SESSION_MFA_VERIFIED_AT, None)
    return _no_store(Response({"detail": "MFA disabled."}))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def regenerate_recovery_codes(request: Request) -> Response:
    if not services.is_feature_enabled():
        return _disabled()
    if services.is_locked_out(request.user):
        return _error(services.LockedOut("Too many failed attempts. Try again later."))
    if not _password_confirmed(request):
        return _password_error()
    try:
        codes = services.regenerate_recovery_codes(request.user, request.data.get("code"))
    except services.MfaError as exc:
        return _error(exc)
    return _no_store(Response({"recovery_codes": codes}))


@api_view(["POST"])
@permission_classes([AllowAny])
def complete_login_challenge(request: Request) -> Response:
    """Second login step: ``{"mfa_token": ..., "code": ...}`` -> session cookie."""
    if not services.is_feature_enabled():
        return _disabled()
    try:
        user = challenge.complete_challenge(request.data.get("mfa_token"), request.data.get("code"))
    except services.MfaError as exc:
        return _error(exc)
    login(request, user)  # rotates the session id
    request.session[SESSION_MFA_VERIFIED_AT] = int(time.time())
    profile = getattr(user, "profile", None)
    return _no_store(
        Response(
            {
                "mfa_required": False,
                "user": {
                    "id": user.pk,
                    "username": user.get_username(),
                    "role": getattr(profile, "role", None),
                    "mfa_enabled": True,
                },
            }
        )
    )
