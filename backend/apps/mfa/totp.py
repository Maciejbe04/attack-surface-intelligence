"""TOTP (RFC 6238) primitives: secret generation and constant-time code matching."""

from __future__ import annotations

import hmac
import re
import time

import pyotp

TOTP_DIGITS = 6
TOTP_PERIOD_SECONDS = 30
# Accept one step of clock drift in each direction (codes valid for ~90 s).
TOTP_DRIFT_STEPS = 1
# 32 base32 characters = 160 bits, the key length recommended by RFC 4226.
SECRET_LENGTH = 32

_CODE_PATTERN = re.compile(rf"^\d{{{TOTP_DIGITS}}}$")


def generate_secret() -> str:
    """Return a new random base32 secret from the OS CSPRNG."""
    return pyotp.random_base32(length=SECRET_LENGTH)


def provisioning_uri(secret: str, *, account_name: str, issuer: str) -> str:
    """``otpauth://`` URI for authenticator apps (QR code content)."""
    return pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_PERIOD_SECONDS).provisioning_uri(
        name=account_name, issuer_name=issuer
    )


def normalize_code(code: object) -> str:
    """Strip whitespace that users often type or paste inside the code."""
    return "".join(str(code or "").split())


def looks_like_totp(code: object) -> bool:
    return bool(_CODE_PATTERN.fullmatch(normalize_code(code)))


def _now() -> float:
    """Clock used for TOTP steps (separate function so tests can freeze it)."""
    return time.time()


def current_step(now: float | None = None) -> int:
    return int(_now() if now is None else now) // TOTP_PERIOD_SECONDS


def match_step(secret: str, code: object, *, now: float | None = None) -> int | None:
    """Return the time step ``code`` belongs to, or ``None`` when it does not match.

    Every candidate step is compared with ``hmac.compare_digest`` and the loop
    never exits early, so timing does not reveal which step matched.
    Callers must store the returned step and reject steps already used
    (replay protection); this function does not do that by itself.
    """
    candidate = normalize_code(code)
    if not secret or not _CODE_PATTERN.fullmatch(candidate):
        return None
    totp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_PERIOD_SECONDS)
    step_now = current_step(now)
    matched: int | None = None
    for step in range(step_now - TOTP_DRIFT_STEPS, step_now + TOTP_DRIFT_STEPS + 1):
        if hmac.compare_digest(totp.generate_otp(step), candidate):
            matched = step
    return matched
