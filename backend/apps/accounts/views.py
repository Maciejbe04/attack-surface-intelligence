from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .mfa import consume_pending_mfa, issue_pending_mfa, verify_totp
from .models import UserProfile
from .permissions import IsAdmin


def _serialize_user(user: User) -> dict:
    profile, _ = UserProfile.objects.get_or_create(user=user)
    # Avoid stale select_related() cache after role/MFA updates in the same request.
    profile.refresh_from_db()
    return {
        "id": user.id,
        "username": user.username,
        "role": profile.role,
        "mfa_enabled": profile.mfa_enabled,
        "is_active": user.is_active,
    }


VALID_ROLES = {choice.value for choice in UserProfile.Role}


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
    return Response(
        {
            "mfa_required": False,
            "user": _serialize_user(user),
            # Header fallback for browsers that drop the session cookie.
            "sessionid": request.session.session_key,
        }
    )


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
    return Response(
        {
            "mfa_required": False,
            "user": _serialize_user(user),
            "sessionid": request.session.session_key,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request: Request) -> Response:
    logout(request)
    return Response({"detail": "Signed out."})


def _record_user_audit(actor: User, action: str, target: User, summary: str) -> None:
    try:
        from apps.scans.audit import record_audit

        record_audit(
            actor=actor,
            action=action,
            object_type="user",
            object_id=target.pk,
            summary=summary,
        )
    except Exception:
        pass


class UserListCreateView(APIView):
    permission_classes = (IsAuthenticated, IsAdmin)

    def get(self, request: Request) -> Response:
        users = User.objects.select_related("profile").order_by("username")
        return Response({"results": [_serialize_user(user) for user in users]})

    def post(self, request: Request) -> Response:
        username = str(request.data.get("username", "")).strip()
        password = str(request.data.get("password", ""))
        role = str(request.data.get("role", UserProfile.Role.VIEWER)).strip().lower()
        if not username or not password:
            return Response(
                {"detail": "Username and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if role not in VALID_ROLES:
            return Response(
                {"detail": f"role must be one of: {', '.join(sorted(VALID_ROLES))}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if User.objects.filter(username__iexact=username).exists():
            return Response(
                {"detail": "Username already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = User.objects.create_user(username=username, password=password)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = role
        profile.save(update_fields=["role"])
        _record_user_audit(
            request.user,
            "user.create",
            user,
            f"Created user {user.username} ({role})",
        )
        return Response(_serialize_user(user), status=status.HTTP_201_CREATED)


class UserDetailView(APIView):
    permission_classes = (IsAuthenticated, IsAdmin)

    def patch(self, request: Request, user_id: int) -> Response:
        user = get_object_or_404(User.objects.select_related("profile"), pk=user_id)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        changed: list[str] = []

        if "role" in request.data:
            role = str(request.data.get("role", "")).strip().lower()
            if role not in VALID_ROLES:
                return Response(
                    {"detail": f"role must be one of: {', '.join(sorted(VALID_ROLES))}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if user.pk == request.user.pk and role != "admin":
                return Response(
                    {"detail": "You cannot remove your own admin role."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            profile.role = role
            profile.save(update_fields=["role"])
            changed.append(f"role={role}")

        if "password" in request.data:
            password = str(request.data.get("password", ""))
            if len(password) < 8:
                return Response(
                    {"detail": "Password must be at least 8 characters."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.set_password(password)
            user.save(update_fields=["password"])
            changed.append("password")

        if "is_active" in request.data:
            is_active = bool(request.data.get("is_active"))
            if user.pk == request.user.pk and not is_active:
                return Response(
                    {"detail": "You cannot disable your own account."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.is_active = is_active
            user.save(update_fields=["is_active"])
            changed.append(f"active={is_active}")

        if not changed:
            return Response(
                {"detail": "No changes provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        _record_user_audit(
            request.user,
            "user.update",
            user,
            f"Updated user {user.username}: {', '.join(changed)}",
        )
        return Response(_serialize_user(user))

    def delete(self, request: Request, user_id: int) -> Response:
        user = get_object_or_404(User, pk=user_id)
        if user.pk == request.user.pk:
            return Response(
                {"detail": "You cannot delete your own account."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        username = user.username
        user.delete()
        try:
            from apps.scans.audit import record_audit

            record_audit(
                actor=request.user,
                action="user.delete",
                object_type="user",
                object_id=user_id,
                summary=f"Deleted user {username}",
            )
        except Exception:
            pass
        return Response(status=status.HTTP_204_NO_CONTENT)
