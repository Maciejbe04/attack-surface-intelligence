"""Authenticated encryption and keyed hashing for MFA data.

Every sensitive value is encrypted with AES-256-GCM. The 256-bit key is never
used directly: a separate subkey is derived per purpose with HKDF-SHA256 from
the master secret ``APP_DATA_KEY`` (Docker secret ``app_data_key``). A leaked
subkey for one purpose therefore does not expose data of another purpose.

Encrypted blob layout (bytes)::

    version (1) | key_id (4) | nonce (12) | ciphertext || GCM tag (16)

``key_id`` identifies the subkey, so old ciphertexts keep working after key
rotation as long as the previous master key is listed in
``APP_DATA_KEY_PREVIOUS``. The caller passes associated data (for example the
user id), which binds a ciphertext to its owner: a blob copied into another
user's row fails authentication.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

BLOB_VERSION = 1
MIN_MASTER_KEY_LENGTH = 32

_KEY_ID_LENGTH = 4
_NONCE_LENGTH = 12
_TAG_LENGTH = 16
_HEADER_LENGTH = 1 + _KEY_ID_LENGTH + _NONCE_LENGTH
_HKDF_SALT = b"surfacex/app-data/v1"


class DecryptionError(Exception):
    """Ciphertext is malformed, was tampered with, or no key can open it."""


@dataclass(frozen=True)
class _Subkey:
    key_id: bytes
    key: bytes


def _master_keys() -> list[str]:
    """Return master keys, current first. Fails closed when misconfigured."""
    current = (getattr(settings, "APP_DATA_KEY", "") or "").strip()
    if len(current) < MIN_MASTER_KEY_LENGTH:
        raise ImproperlyConfigured(
            "APP_DATA_KEY is missing or shorter than "
            f"{MIN_MASTER_KEY_LENGTH} characters; sensitive data cannot be protected. "
            "Generate it with scripts/init-secrets.sh."
        )
    keys = [current]
    previous = getattr(settings, "APP_DATA_KEY_PREVIOUS", "") or ""
    for candidate in previous.split(","):
        candidate = candidate.strip()
        if not candidate:
            continue
        if len(candidate) < MIN_MASTER_KEY_LENGTH:
            raise ImproperlyConfigured("APP_DATA_KEY_PREVIOUS contains a key that is too short.")
        if candidate not in keys:
            keys.append(candidate)
    return keys


@lru_cache(maxsize=32)
def _derive(master_key: str, purpose: str) -> _Subkey:
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_HKDF_SALT,
        info=f"surfacex:{purpose}".encode(),
    ).derive(master_key.encode())
    key_id = hashlib.sha256(b"surfacex:key-id:" + key).digest()[:_KEY_ID_LENGTH]
    return _Subkey(key_id=key_id, key=key)


def _associated_data(purpose: str, aad: bytes) -> bytes:
    return b"surfacex|" + purpose.encode() + b"|" + aad


def encrypt(plaintext: bytes, *, purpose: str, aad: bytes) -> bytes:
    """Encrypt ``plaintext`` with the current key. A fresh random nonce is used every time."""
    subkey = _derive(_master_keys()[0], purpose)
    nonce = os.urandom(_NONCE_LENGTH)
    ciphertext = AESGCM(subkey.key).encrypt(nonce, plaintext, _associated_data(purpose, aad))
    return bytes([BLOB_VERSION]) + subkey.key_id + nonce + ciphertext


def decrypt(blob: bytes | memoryview, *, purpose: str, aad: bytes) -> bytes:
    """Decrypt a blob produced by :func:`encrypt`. Raises :class:`DecryptionError`."""
    data = bytes(blob)
    if len(data) < _HEADER_LENGTH + _TAG_LENGTH or data[0] != BLOB_VERSION:
        raise DecryptionError("Unsupported or truncated ciphertext.")
    key_id = data[1 : 1 + _KEY_ID_LENGTH]
    nonce = data[1 + _KEY_ID_LENGTH : _HEADER_LENGTH]
    ciphertext = data[_HEADER_LENGTH:]
    for master_key in _master_keys():
        subkey = _derive(master_key, purpose)
        if not hmac.compare_digest(subkey.key_id, key_id):
            continue
        try:
            return AESGCM(subkey.key).decrypt(nonce, ciphertext, _associated_data(purpose, aad))
        except InvalidTag as exc:
            raise DecryptionError("Ciphertext failed authentication.") from exc
    raise DecryptionError("No configured key matches this ciphertext.")


def needs_rotation(blob: bytes | memoryview, *, purpose: str) -> bool:
    """True when the blob was encrypted with a key other than the current one."""
    data = bytes(blob)
    current = _derive(_master_keys()[0], purpose)
    return not hmac.compare_digest(data[1 : 1 + _KEY_ID_LENGTH], current.key_id)


def keyed_digest(value: bytes, *, purpose: str) -> str:
    """HMAC-SHA256 of ``value`` under the current key (hex). For high-entropy values only."""
    return keyed_digests(value, purpose=purpose)[0]


def keyed_digests(value: bytes, *, purpose: str) -> list[str]:
    """HMAC-SHA256 of ``value`` under every configured key, current first.

    Lookups use all of them so stored digests stay valid during key rotation.
    """
    return [
        hmac.new(_derive(master_key, purpose).key, value, hashlib.sha256).hexdigest()
        for master_key in _master_keys()
    ]
