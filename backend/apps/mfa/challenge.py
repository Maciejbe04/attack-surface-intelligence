"""Login challenge: the short-lived step between a correct password and a session.

After the password is accepted, the login view calls :func:`issue_challenge`
and returns the token to the client instead of creating a session. The client
then sends the token with a code to :func:`complete_challenge`.

* The token has 256 bits of entropy. Only its SHA-256 hash is used as the
  cache key, so a dump of Redis does not reveal live tokens.
* A token is single use, expires after ``CHALLENGE_TTL_SECONDS`` and dies
  after ``MAX_ATTEMPTS`` wrong codes. A failed code never mints a new token,
  so brute force requires the password again for every few guesses.
"""

from __future__ import annotations

import hashlib
import secrets
import time

from django.contrib.auth import get_user_model
from django.core.cache import cache

from . import services

CHALLENGE_TTL_SECONDS = 300
MAX_ATTEMPTS = 5
_PREFIX = "mfa:challenge:"


class ChallengeInvalid(services.MfaError):
    code = "challenge_invalid"


def _cache_key(token: str) -> str:
    return _PREFIX + hashlib.sha256(token.encode()).hexdigest()


def issue_challenge(user) -> str:
    token = secrets.token_urlsafe(32)
    cache.set(
        _cache_key(token),
        {"user_id": user.pk, "attempts": 0, "expires_at": time.time() + CHALLENGE_TTL_SECONDS},
        timeout=CHALLENGE_TTL_SECONDS,
    )
    return token


def complete_challenge(token: object, code: object):
    """Return the user when ``code`` is valid for the challenge ``token``.

    Raises :class:`ChallengeInvalid`, :class:`services.InvalidCode` or
    :class:`services.LockedOut`.
    """
    token = str(token or "").strip()
    if not token or len(token) > 128:
        raise ChallengeInvalid("MFA challenge expired or invalid. Sign in again.")
    key = _cache_key(token)
    payload = cache.get(key)
    if not payload:
        raise ChallengeInvalid("MFA challenge expired or invalid. Sign in again.")

    user = get_user_model().objects.filter(pk=payload["user_id"], is_active=True).first()
    if user is None:
        cache.delete(key)
        raise ChallengeInvalid("MFA challenge expired or invalid. Sign in again.")

    try:
        services.verify_second_factor(user, code)
    except services.InvalidCode:
        attempts = int(payload["attempts"]) + 1
        remaining_ttl = int(payload["expires_at"] - time.time())
        if attempts >= MAX_ATTEMPTS or remaining_ttl <= 0:
            cache.delete(key)
            raise ChallengeInvalid("Too many invalid codes. Sign in again.") from None
        payload["attempts"] = attempts
        cache.set(key, payload, timeout=remaining_ttl)
        raise
    except services.MfaError:
        cache.delete(key)
        raise

    cache.delete(key)
    return user
