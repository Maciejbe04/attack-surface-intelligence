from __future__ import annotations

import secrets
from dataclasses import dataclass

import pyotp
from django.core.cache import cache


MFA_PENDING_PREFIX = "mfa_pending:"
MFA_PENDING_TTL = 300


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


def issue_pending_mfa(user_id: int, username: str) -> str:
    token = secrets.token_urlsafe(32)
    cache.set(
        f"{MFA_PENDING_PREFIX}{token}",
        {"user_id": user_id, "username": username},
        timeout=MFA_PENDING_TTL,
    )
    return token


def consume_pending_mfa(token: str) -> PendingMfa | None:
    key = f"{MFA_PENDING_PREFIX}{token}"
    payload = cache.get(key)
    if not payload:
        return None
    cache.delete(key)
    return PendingMfa(user_id=int(payload["user_id"]), username=str(payload["username"]))
