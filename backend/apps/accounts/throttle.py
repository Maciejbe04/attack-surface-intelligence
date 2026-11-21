"""Brute-force protection for password sign-in (API login and Django admin).

Failed attempts are counted in the cache (Redis in Docker, shared by all
gunicorn workers) under three keys, each with a fixed 15-minute window:

* username + client IP: stops a single attacker guessing one account;
* username alone: stops the same guessing spread over many IPs;
* client IP alone: stops one IP trying many accounts (password spraying).

Usernames and IPs are hashed in the key names, so a cache dump does not list them.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("surfacex.security.auth")

WINDOW_SECONDS = 15 * 60
MAX_FAILURES_PER_USER_AND_IP = 5
MAX_FAILURES_PER_USER = 20
MAX_FAILURES_PER_IP = 50

_PREFIX = "auth:fail:"


def client_ip(request) -> str:
    """Client address. Behind the gateway, nginx sets X-Real-IP (overwriting any client value)."""
    if request is None:
        return "unknown"
    candidates = []
    if getattr(settings, "TRUST_X_REAL_IP", True):
        candidates.append(request.META.get("HTTP_X_REAL_IP", ""))
    candidates.append(request.META.get("REMOTE_ADDR", ""))
    for candidate in candidates:
        candidate = (candidate or "").strip()
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            continue
    return "unknown"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def _keys(username: str, ip: str) -> dict[str, tuple[str, int]]:
    user = _digest((username or "").strip().lower())
    addr = _digest(ip)
    return {
        "user_ip": (f"{_PREFIX}ui:{user}:{addr}", MAX_FAILURES_PER_USER_AND_IP),
        "user": (f"{_PREFIX}u:{user}", MAX_FAILURES_PER_USER),
        "ip": (f"{_PREFIX}ip:{addr}", MAX_FAILURES_PER_IP),
    }


def is_locked(username: str, ip: str) -> bool:
    for key, limit in _keys(username, ip).values():
        if int(cache.get(key, 0)) >= limit:
            return True
    return False


def record_failure(username: str, ip: str) -> None:
    for name, (key, limit) in _keys(username, ip).items():
        cache.add(key, 0, timeout=WINDOW_SECONDS)
        try:
            count = cache.incr(key)
        except ValueError:  # expired between add() and incr()
            cache.set(key, 1, timeout=WINDOW_SECONDS)
            count = 1
        if count == limit:
            logger.warning("auth.lockout scope=%s ip=%s window=%ss", name, ip, WINDOW_SECONDS)


def reset_user(username: str, ip: str) -> None:
    """Clear per-account counters after a successful sign-in. The per-IP counter stays."""
    keys = _keys(username, ip)
    cache.delete_many([keys["user_ip"][0], keys["user"][0]])
