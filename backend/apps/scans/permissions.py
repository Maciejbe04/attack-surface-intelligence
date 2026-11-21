from django.contrib.auth.models import User
from rest_framework.permissions import BasePermission
from rest_framework.request import Request


def role_for(user: User) -> str:
    if user.is_superuser:
        return "admin"
    try:
        return user.profile.role
    except User.profile.RelatedObjectDoesNotExist:
        return "viewer"


class IsAdminOrOperator(BasePermission):
    message = "Admin or operator role required."

    def has_permission(self, request: Request, view: object) -> bool:
        return bool(
            request.user.is_authenticated
            and role_for(request.user) in {"admin", "operator"}
        )
