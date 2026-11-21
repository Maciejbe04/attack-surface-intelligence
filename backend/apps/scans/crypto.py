"""Envelope encryption for sensitive scan evidence (AES-256-GCM)."""

from __future__ import annotations

import base64
import hashlib
import os
from typing import Any

from django.conf import settings

_PREFIX = "sx1:"


def _key_bytes() -> bytes | None:
    raw = (getattr(settings, "APP_DATA_KEY", "") or "").strip()
    if not raw:
        return None
    # Accept base64 secret or arbitrary string hashed to 32 bytes.
    try:
        decoded = base64.b64decode(raw, validate=False)
        if len(decoded) >= 32:
            return decoded[:32]
    except Exception:
        pass
    return hashlib.sha256(raw.encode("utf-8")).digest()


def seal(plaintext: str | bytes) -> str:
    """Encrypt plaintext; returns sx1: envelope or empty string if no key."""
    key = _key_bytes()
    if key is None:
        return ""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        return ""
    data = plaintext.encode("utf-8") if isinstance(plaintext, str) else plaintext
    nonce = os.urandom(12)
    cipher = AESGCM(key).encrypt(nonce, data, None)
    blob = base64.urlsafe_b64encode(nonce + cipher).decode("ascii")
    return f"{_PREFIX}{blob}"


def open_sealed(envelope: str) -> str | None:
    """Decrypt sx1: envelope. Returns None if undecryptable."""
    if not envelope or not envelope.startswith(_PREFIX):
        return None
    key = _key_bytes()
    if key is None:
        return None
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        raw = base64.urlsafe_b64decode(envelope[len(_PREFIX) :].encode("ascii"))
        nonce, cipher = raw[:12], raw[12:]
        return AESGCM(key).decrypt(nonce, cipher, None).decode("utf-8")
    except Exception:
        return None


def seal_json(payload: dict[str, Any]) -> str:
    import json

    return seal(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
