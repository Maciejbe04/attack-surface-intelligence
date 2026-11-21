from django.conf import settings
from django.db import models
from django.utils import timezone


class MfaCredential(models.Model):
    """TOTP credential of one user.

    The TOTP secret is stored only as an AES-256-GCM ciphertext bound to the
    user id (see ``apps.mfa.crypto``). Nothing in this table is plaintext.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mfa_credential",
    )
    secret_encrypted = models.BinaryField(editable=False)
    enrollment_started_at = models.DateTimeField(default=timezone.now)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    # Highest TOTP time step accepted so far. Codes from this step or earlier
    # are rejected, so an intercepted code cannot be replayed.
    last_used_step = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "MFA credential"

    @property
    def is_confirmed(self) -> bool:
        return self.confirmed_at is not None

    def __str__(self) -> str:
        return f"MfaCredential(user_id={self.user_id}, confirmed={self.is_confirmed})"

    __repr__ = __str__


class MfaRecoveryCode(models.Model):
    """One-time recovery code, stored only as a keyed HMAC-SHA256 digest."""

    credential = models.ForeignKey(
        MfaCredential,
        on_delete=models.CASCADE,
        related_name="recovery_codes",
    )
    code_digest = models.CharField(max_length=64)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "MFA recovery code"
        constraints = [
            models.UniqueConstraint(
                fields=["credential", "code_digest"],
                name="mfa_recovery_code_unique_per_credential",
            )
        ]

    def __str__(self) -> str:
        return f"MfaRecoveryCode(credential_id={self.credential_id}, used={self.used_at is not None})"

    __repr__ = __str__
