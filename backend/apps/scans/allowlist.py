"""Allowlist matching for targets and resolved IPs."""

from __future__ import annotations

import ipaddress
import socket
from typing import Iterable

from django.contrib.auth.models import User

from .models import AllowlistEntry, Target
from .validation import normalize_target


class AllowlistDenied(ValueError):
    """Raised when a target or resolved address is outside the allowlist."""


def owner_allowlist_active(owner: User) -> bool:
    return AllowlistEntry.objects.filter(owner=owner, enabled=True).exists()


def _domain_matches(candidate: str, allowed: str) -> bool:
    candidate = candidate.lower().rstrip(".")
    allowed = allowed.lower().rstrip(".")
    return candidate == allowed or candidate.endswith(f".{allowed}")


def is_value_allowed(owner: User, value: str, value_type: str | None = None) -> bool:
    """Return True if value is allowed. Empty allowlist ⇒ open (compat)."""
    entries = list(
        AllowlistEntry.objects.filter(owner=owner, enabled=True).only(
            "value", "entry_type"
        )
    )
    if not entries:
        return True

    kind = (value_type or "").strip().lower()
    raw = value.strip()
    if not kind:
        try:
            ipaddress.ip_address(raw)
            kind = "ip"
        except ValueError:
            try:
                ipaddress.ip_network(raw, strict=False)
                kind = "cidr"
            except ValueError:
                kind = "domain"

    try:
        normalized = normalize_target(raw, kind)
    except ValueError:
        return False

    if kind == "ip":
        addr = ipaddress.ip_address(normalized)
        for entry in entries:
            if entry.entry_type == "ip" and entry.value == normalized:
                return True
            if entry.entry_type == "cidr":
                try:
                    if addr in ipaddress.ip_network(entry.value, strict=False):
                        return True
                except ValueError:
                    continue
        return False

    if kind == "cidr":
        try:
            network = ipaddress.ip_network(normalized, strict=False)
        except ValueError:
            return False
        for entry in entries:
            if entry.entry_type == "cidr" and entry.value == normalized:
                return True
            if entry.entry_type == "ip":
                try:
                    if ipaddress.ip_address(entry.value) in network and network.num_addresses == 1:
                        return True
                except ValueError:
                    continue
        return False

    # domain
    for entry in entries:
        if entry.entry_type == "domain" and _domain_matches(normalized, entry.value):
            return True
    return False


def assert_target_allowed(owner: User, address: str, target_type: str) -> None:
    if not is_value_allowed(owner, address, target_type):
        raise AllowlistDenied(
            f"Target {address} is outside the allowlist. Add it under System → Allowlist."
        )


def resolve_ips(hostname: str) -> list[str]:
    ips: list[str] = []
    try:
        for family, _, _, _, sockaddr in socket.getaddrinfo(
            hostname, None, type=socket.SOCK_STREAM
        ):
            if family in (socket.AF_INET, socket.AF_INET6):
                ips.append(sockaddr[0])
    except socket.gaierror as exc:
        raise AllowlistDenied(f"DNS resolution failed for {hostname}: {exc}") from exc
    # unique preserve order
    seen: set[str] = set()
    out: list[str] = []
    for ip in ips:
        if ip not in seen:
            seen.add(ip)
            out.append(ip)
    return out


def assert_resolvable_allowed(owner: User, address: str, target_type: str) -> list[str]:
    """Check allowlist for the target; for domains also re-check every resolved IP."""
    assert_target_allowed(owner, address, target_type)
    if target_type != Target.Type.DOMAIN and target_type != "domain":
        return []
    resolved = resolve_ips(address)
    denied = [ip for ip in resolved if not is_value_allowed(owner, ip, "ip")]
    if denied:
        raise AllowlistDenied(
            f"Resolved address(es) for {address} outside allowlist: {', '.join(denied)}"
        )
    return resolved


def filter_allowed_targets(owner: User, targets: Iterable[Target]) -> tuple[list[Target], list[str]]:
    allowed: list[Target] = []
    rejected: list[str] = []
    for target in targets:
        if is_value_allowed(owner, target.address, target.target_type):
            allowed.append(target)
        else:
            rejected.append(target.address)
    return allowed, rejected
