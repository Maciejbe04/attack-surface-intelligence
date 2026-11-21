"""MFA business logic: enrollment, verification, recovery codes, lockout.

Security properties:

* TOTP secrets are encrypted at rest (AES-256-GCM, bound to the user id) and
  decrypted only in memory for the moment of verification.
* Recovery codes have about 50 bits of entropy, are shown once and stored only
  as keyed HMAC-SHA256 digests. Each one works once.
* A TOTP code cannot be reused: the accepted time step is stored and older or
  equal steps are rejected atomically in the database.
* Repeated failures lock second-factor checks for the user for a while.
* Nothing here logs or returns a secret, except the values that must be shown
  to the user exactly once (new TOTP secret, new recovery codes).
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from . import crypto, totp
from .models import MfaCredential, MfaRecoveryCode

logger = logging.getLogger("surfacex.security.mfa")

SECRET_PURPOSE = "mfa-totp-secret"
RECOVERY_PURPOSE = "mfa-recovery-code"

ENROLLMENT_TTL = timedelta(minutes=15)
RECOVERY_CODE_COUNT = 10
# Crockford-like alphabet without 0/O/1/I: 32 symbols = 5 bits per character.
RECOVERY_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
RECOVERY_CODE_LENGTH = 10  # 50 bits of entropy

MAX_FAILED_ATTEMPTS = 10
LOCKOUT_SECONDS = 15 * 60


class MfaError(Exception):
    """Base class. ``code`` is a stable machine-readable identifier for the API."""

    code = "mfa_error"


class NotEnrolled(MfaError):
    code = "not_enrolled"


class AlreadyEnrolled(MfaError):
    code = "already_enrolled"


class EnrollmentExpired(MfaError):
    code = "enrollment_expired"


class InvalidCode(MfaError):
    code = "invalid_code"


class LockedOut(MfaError):
    code = "locked_out"


@dataclass(frozen=True)
class Enrollment:
    """Returned once to the user; never persisted in this form."""

    secret: str
    otpauth_uri: str
    expires_in_seconds: int


# --------------------------------------------------------------------------- flags


def is_feature_enabled() -> bool:
    """MFA stays dormant until ``MFA_ENABLED=1`` is set for the API."""
    return bool(getattr(settings, "MFA_ENABLED", False))


def user_has_mfa(user) -> bool:
    return MfaCredential.objects.filter(user=user, confirmed_at__isnull=False).exists()


def login_requires_mfa(user) -> bool:
    """Hook for the login view: True means password alone must not create a session."""
    return is_feature_enabled() and user_has_mfa(user)


# --------------------------------------------------------------------------- secrets


def _aad(user_id: int) -> bytes:
    return f"user:{user_id}".encode()


def _encrypt_secret(user_id: int, secret: str) -> bytes:
    return crypto.encrypt(secret.encode(), purpose=SECRET_PURPOSE, aad=_aad(user_id))


def _decrypt_secret(credential: MfaCredential) -> str:
    return crypto.decrypt(
        credential.secret_encrypted, purpose=SECRET_PURPOSE, aad=_aad(credential.user_id)
    ).decode()


def _issuer() -> str:
    return getattr(settings, "MFA_ISSUER", "SurfaceX")


# --------------------------------------------------------------------------- lockout


def _failure_key(user_id: int) -> str:
    return f"mfa:failures:{user_id}"


def is_locked_out(user) -> bool:
    return int(cache.get(_failure_key(user.pk), 0)) >= MAX_FAILED_ATTEMPTS


def _ensure_not_locked(user) -> None:
    if is_locked_out(user):
        logger.warning("mfa.locked_out_attempt user_id=%s", user.pk)
        raise LockedOut("Too many failed attempts. Try again later.")


def record_failed_attempt(user) -> None:
    """Count a failed second-factor or password confirmation for ``user``."""
    key = _failure_key(user.pk)
    cache.add(key, 0, timeout=LOCKOUT_SECONDS)
    try:
        failures = cache.incr(key)
    except ValueError:  # key expired between add() and incr()
        cache.set(key, 1, timeout=LOCKOUT_SECONDS)
        failures = 1
    logger.info("mfa.failed_attempt user_id=%s failures=%s", user.pk, failures)
    if failures == MAX_FAILED_ATTEMPTS:
        logger.warning("mfa.lockout user_id=%s seconds=%s", user.pk, LOCKOUT_SECONDS)


def _clear_failures(user) -> None:
    cache.delete(_failure_key(user.pk))


# --------------------------------------------------------------------------- recovery codes


def _generate_recovery_code() -> str:
    raw = "".join(secrets.choice(RECOVERY_CODE_ALPHABET) for _ in range(RECOVERY_CODE_LENGTH))
    half = RECOVERY_CODE_LENGTH // 2
    return f"{raw[:half]}-{raw[half:]}"


def _canonical_recovery_code(code: object) -> str | None:
    canonical = "".join(str(code or "").split()).replace("-", "").upper()
    if len(canonical) != RECOVERY_CODE_LENGTH:
        return None
    if any(char not in RECOVERY_CODE_ALPHABET for char in canonical):
        return None
    return canonical


def _recovery_digest_input(user_id: int, canonical: str) -> bytes:
    return f"{user_id}:{canonical}".encode()


def _replace_recovery_codes(credential: MfaCredential) -> list[str]:
    credential.recovery_codes.all().delete()
    codes = [_generate_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
    MfaRecoveryCode.objects.bulk_create(
        MfaRecoveryCode(
            credential=credential,
            code_digest=crypto.keyed_digest(
                _recovery_digest_input(credential.user_id, _canonical_recovery_code(code)),
                purpose=RECOVERY_PURPOSE,
            ),
        )
        for code in codes
    )
    return codes


def _consume_recovery_code(credential: MfaCredential, code: object) -> bool:
    canonical = _canonical_recovery_code(code)
    if canonical is None:
        return False
    digests = crypto.keyed_digests(
        _recovery_digest_input(credential.user_id, canonical), purpose=RECOVERY_PURPOSE
    )
    # Atomic single use: two concurrent requests cannot both consume the same code.
    used = MfaRecoveryCode.objects.filter(
        credential=credential, code_digest__in=digests, used_at__isnull=True
    ).update(used_at=timezone.now())
    return used > 0


def remaining_recovery_codes(user) -> int:
    return MfaRecoveryCode.objects.filter(
        credential__user=user, credential__confirmed_at__isnull=False, used_at__isnull=True
    ).count()


# --------------------------------------------------------------------------- enrollment


@transaction.atomic
def start_enrollment(user) -> Enrollment:
    """Create (or restart) an unconfirmed credential and return the secret once."""
    credential = MfaCredential.objects.select_for_update().filter(user=user).first()
    if credential is not None and credential.is_confirmed:
        raise AlreadyEnrolled("MFA is already enabled for this account.")

    secret = totp.generate_secret()
    encrypted = _encrypt_secret(user.pk, secret)
    if credential is None:
        MfaCredential.objects.create(user=user, secret_encrypted=encrypted)
    else:
        credential.secret_encrypted = encrypted
        credential.enrollment_started_at = timezone.now()
        credential.last_used_step = 0
        credential.save(update_fields=["secret_encrypted", "enrollment_started_at", "last_used_step", "updated_at"])

    logger.info("mfa.enrollment_started user_id=%s", user.pk)
    return Enrollment(
        secret=secret,
        otpauth_uri=totp.provisioning_uri(secret, account_name=user.get_username(), issuer=_issuer()),
        expires_in_seconds=int(ENROLLMENT_TTL.total_seconds()),
    )


@transaction.atomic
def confirm_enrollment(user, code: object) -> list[str]:
    """Activate MFA after the user proves the authenticator works. Returns recovery codes once."""
    _ensure_not_locked(user)
    credential = MfaCredential.objects.select_for_update().filter(user=user).first()
    if credential is None:
        raise NotEnrolled("Start MFA enrollment first.")
    if credential.is_confirmed:
        raise AlreadyEnrolled("MFA is already enabled for this account.")
    if timezone.now() - credential.enrollment_started_at > ENROLLMENT_TTL:
        # No delete here: raising rolls the transaction back anyway. The stale
        # row is overwritten by the next start_enrollment() call.
        logger.info("mfa.enrollment_expired user_id=%s", user.pk)
        raise EnrollmentExpired("Enrollment expired. Start again.")

    step = totp.match_step(_decrypt_secret(credential), code)
    if step is None:
        record_failed_attempt(user)
        raise InvalidCode("Invalid authentication code.")

    credential.confirmed_at = timezone.now()
    credential.last_used_step = step
    credential.save(update_fields=["confirmed_at", "last_used_step", "updated_at"])
    codes = _replace_recovery_codes(credential)
    _clear_failures(user)
    logger.info("mfa.enrolled user_id=%s", user.pk)
    return codes


def get_pending_enrollment(user) -> MfaCredential | None:
    return MfaCredential.objects.filter(user=user, confirmed_at__isnull=True).first()


# --------------------------------------------------------------------------- verification


def verify_second_factor(user, code: object, *, allow_recovery_code: bool = True) -> str:
    """Check a TOTP or recovery code. Returns ``"totp"`` or ``"recovery_code"``.

    Raises :class:`LockedOut`, :class:`NotEnrolled` or :class:`InvalidCode`.
    """
    _ensure_not_locked(user)
    credential = MfaCredential.objects.filter(user=user, confirmed_at__isnull=False).first()
    if credential is None:
        raise NotEnrolled("MFA is not enabled for this account.")

    if totp.looks_like_totp(code):
        step = totp.match_step(_decrypt_secret(credential), code)
        if step is not None:
            accepted = MfaCredential.objects.filter(
                pk=credential.pk, last_used_step__lt=step
            ).update(last_used_step=step)
            if accepted:
                _clear_failures(user)
                logger.info("mfa.verified user_id=%s method=totp", user.pk)
                return "totp"
            logger.warning("mfa.replay_rejected user_id=%s", user.pk)
    elif allow_recovery_code and _consume_recovery_code(credential, code):
        _clear_failures(user)
        logger.warning(
            "mfa.recovery_code_used user_id=%s remaining=%s",
            user.pk,
            remaining_recovery_codes(user),
        )
        return "recovery_code"

    record_failed_attempt(user)
    raise InvalidCode("Invalid authentication code.")


@transaction.atomic
def regenerate_recovery_codes(user, code: object) -> list[str]:
    """Replace all recovery codes. Requires a valid TOTP code (not a recovery code)."""
    verify_second_factor(user, code, allow_recovery_code=False)
    credential = MfaCredential.objects.select_for_update().get(user=user, confirmed_at__isnull=False)
    codes = _replace_recovery_codes(credential)
    logger.info("mfa.recovery_codes_regenerated user_id=%s", user.pk)
    return codes


@transaction.atomic
def disable(user, code: object) -> None:
    """Turn MFA off for ``user`` after verifying a second factor."""
    verify_second_factor(user, code)
    MfaCredential.objects.filter(user=user).delete()
    _clear_failures(user)
    logger.warning("mfa.disabled user_id=%s", user.pk)


def admin_reset(user) -> bool:
    """Remove MFA without a code (lost device). Only for trusted operator tooling."""
    deleted, _ = MfaCredential.objects.filter(user=user).delete()
    _clear_failures(user)
    if deleted:
        logger.warning("mfa.admin_reset user_id=%s", user.pk)
    return bool(deleted)


def rotate_encryption(batch_size: int = 500) -> int:
    """Re-encrypt TOTP secrets still using an old ``APP_DATA_KEY``. Returns how many changed."""
    rotated = 0
    for credential in MfaCredential.objects.iterator(chunk_size=batch_size):
        if not crypto.needs_rotation(credential.secret_encrypted, purpose=SECRET_PURPOSE):
            continue
        with transaction.atomic():
            locked = MfaCredential.objects.select_for_update().get(pk=credential.pk)
            locked.secret_encrypted = _encrypt_secret(locked.user_id, _decrypt_secret(locked))
            locked.save(update_fields=["secret_encrypted", "updated_at"])
        rotated += 1
    if rotated:
        logger.info("mfa.secrets_rotated count=%s", rotated)
    return rotated
