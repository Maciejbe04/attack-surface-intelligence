from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

import pyotp
from django.core.cache import cache


MFA_PENDING_PREFIX = "mfa_pending:"
MFA_PENDING_TTL = 300
MFA_PENDING_MAX_ATTEMPTS = 5


@dataclass
class PendingMfa:
    user_id: int
    username: str


def new_totp_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, username: str, issuer: str = "SurfaceX") -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)


def verify_totp(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    totp = pyotp.TOTP(secret)
    return totp.verify(code.strip(), valid_window=1)


def _pending_key(token: str) -> str:
    # Only a hash of the token is stored, so a cache dump does not reveal live tokens.
    return MFA_PENDING_PREFIX + hashlib.sha256(token.encode()).hexdigest()


def issue_pending_mfa(user_id: int, username: str) -> str:
    token = secrets.token_urlsafe(32)
    cache.set(
        _pending_key(token),
        {"user_id": user_id, "username": username, "attempts": 0},
        timeout=MFA_PENDING_TTL,
    )
    return token


def get_pending_mfa(token: str) -> PendingMfa | None:
    if not token or len(token) > 128:
        return None
    payload = cache.get(_pending_key(token))
    if not payload:
        return None
    return PendingMfa(user_id=int(payload["user_id"]), username=str(payload["username"]))


def register_pending_mfa_failure(token: str) -> bool:
    """Count a wrong code. Returns False (and kills the token) after the last allowed attempt."""
    key = _pending_key(token)
    payload = cache.get(key)
    if not payload:
        return False
    payload["attempts"] = int(payload.get("attempts", 0)) + 1
    if payload["attempts"] >= MFA_PENDING_MAX_ATTEMPTS:
        cache.delete(key)
        return False
    cache.set(key, payload, timeout=MFA_PENDING_TTL)
    return True


def discard_pending_mfa(token: str) -> None:
    cache.delete(_pending_key(token))


def consume_pending_mfa(token: str) -> PendingMfa | None:
    pending = get_pending_mfa(token)
    if pending is not None:
        discard_pending_mfa(token)
    return pending
