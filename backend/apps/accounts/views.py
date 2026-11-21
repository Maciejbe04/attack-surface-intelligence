from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from . import throttle
from .mfa import (
    discard_pending_mfa,
    get_pending_mfa,
    issue_pending_mfa,
    register_pending_mfa_failure,
    verify_totp,
)
from .models import UserProfile


def _serialize_user(user: User) -> dict:
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return {
        "id": user.id,
        "username": user.username,
        "role": profile.role,
        "mfa_enabled": profile.mfa_enabled,
    }


@api_view(["GET"])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def csrf(request: Request) -> Response:
    return Response({"csrfToken": get_token(request)})


@api_view(["GET"])
@permission_classes([AllowAny])
def me(request: Request) -> Response:
    if not request.user.is_authenticated:
        return Response({"authenticated": False}, status=status.HTTP_200_OK)
    return Response({"authenticated": True, "user": _serialize_user(request.user)})


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request: Request) -> Response:
    username = str(request.data.get("username", "")).strip()
    password = str(request.data.get("password", ""))
    if not username or not password:
        return Response(
            {"detail": "Username and password are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if throttle.is_locked(username, throttle.client_ip(request)):
        return Response(
            {"detail": "Too many failed sign-in attempts. Try again in 15 minutes."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response(
            {"detail": "Invalid username or password."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    if not user.is_active:
        return Response({"detail": "Account disabled."}, status=status.HTTP_403_FORBIDDEN)

    profile, _ = UserProfile.objects.get_or_create(user=user)
    if profile.mfa_enabled and profile.mfa_secret:
        token = issue_pending_mfa(user.id, user.username)
        return Response(
            {
                "mfa_required": True,
                "mfa_token": token,
                "detail": "Enter the 6-digit code from your authenticator app.",
            }
        )

    login(request, user)
    return Response({"mfa_required": False, "user": _serialize_user(user)})


@api_view(["POST"])
@permission_classes([AllowAny])
def mfa_verify(request: Request) -> Response:
    token = str(request.data.get("mfa_token", "")).strip()
    code = str(request.data.get("code", "")).strip()
    pending = get_pending_mfa(token)
    if pending is None:
        return Response(
            {"detail": "MFA challenge expired or invalid. Sign in again."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    user = User.objects.filter(pk=pending.user_id, is_active=True).first()
    if user is None:
        discard_pending_mfa(token)
        return Response(
            {"detail": "MFA challenge expired or invalid. Sign in again."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    profile, _ = UserProfile.objects.get_or_create(user=user)
    if not verify_totp(profile.mfa_secret, code):
        # Same token, limited attempts: a wrong code never mints a fresh token,
        # so the 6-digit code cannot be brute-forced without the password.
        if not register_pending_mfa_failure(token):
            return Response(
                {"detail": "Too many invalid codes. Sign in again."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(
            {
                "detail": "Invalid authentication code.",
                "mfa_required": True,
                "mfa_token": token,
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    discard_pending_mfa(token)
    login(request, user)
    return Response({"mfa_required": False, "user": _serialize_user(user)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request: Request) -> Response:
    logout(request)
    return Response({"detail": "Signed out."})
