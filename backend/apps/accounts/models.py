from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        OPERATOR = "operator", "Operator"
        ANALYST = "analyst", "Analyst"
        VIEWER = "viewer", "Viewer"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.VIEWER)
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret = models.CharField(max_length=64, blank=True, default="")
    mfa_enforced = models.BooleanField(
        default=False,
        help_text="When true, user must complete MFA before console access.",
    )

    def __str__(self) -> str:
        return f"{self.user.username}:{self.role}"
