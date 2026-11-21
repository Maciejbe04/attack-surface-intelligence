"""Helpers for durable manual overrides."""

from __future__ import annotations

from django.contrib.auth.models import User

from .crypto import open_sealed, seal
from .models import ManualOverride


def notes_plaintext(override: ManualOverride) -> str:
    if override.notes_ciphertext:
        return open_sealed(override.notes_ciphertext) or ""
    return override.notes or ""


def store_notes(override: ManualOverride, text: str) -> None:
    sealed = seal(text or "")
    if sealed and text:
        override.notes_ciphertext = sealed
        override.notes = ""
    else:
        override.notes = text or ""
        override.notes_ciphertext = ""


def effective_attrs(base: dict, override: ManualOverride | None) -> dict:
    if not override:
        return dict(base or {})
    merged = dict(base or {})
    patch = override.attrs_patch if isinstance(override.attrs_patch, dict) else {}
    merged.update(patch)
    return merged


def overrides_for_keys(owner: User, entity_keys: list[str]) -> dict[str, ManualOverride]:
    if not entity_keys:
        return {}
    rows = ManualOverride.objects.filter(owner=owner, entity_key__in=entity_keys)
    return {row.entity_key: row for row in rows}
