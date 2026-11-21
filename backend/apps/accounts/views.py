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

from .mfa import consume_pending_mfa, issue_pending_mfa, verify_totp
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

    user = authenticate(request, username=username, password=password)
    if user is None:
        try:
            from apps.scans.audit import record_audit

            record_audit(
                actor=None,
                action="auth.login_failure",
                object_type="user",
                object_id=username[:64],
                summary=f"Failed login for {username[:64]}",
            )
        except Exception:
            pass
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
    pending = consume_pending_mfa(token)
    if pending is None:
        return Response(
            {"detail": "MFA challenge expired or invalid. Sign in again."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        user = User.objects.get(pk=pending.user_id)
    except User.DoesNotExist:
        return Response({"detail": "User not found."}, status=status.HTTP_401_UNAUTHORIZED)

    profile, _ = UserProfile.objects.get_or_create(user=user)
    if not verify_totp(profile.mfa_secret, code):
        # re-issue so UX can retry without full password again within TTL window
        new_token = issue_pending_mfa(user.id, user.username)
        return Response(
            {
                "detail": "Invalid authentication code.",
                "mfa_required": True,
                "mfa_token": new_token,
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    login(request, user)
    return Response({"mfa_required": False, "user": _serialize_user(user)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request: Request) -> Response:
    logout(request)
    return Response({"detail": "Signed out."})
