"""Scan scope (allowlist) and splitting of large ranges into batches.

Scope is configured with two settings (comma separated in the environment):

* ``SCAN_ALLOWED_NETWORKS`` – CIDRs that may be scanned, e.g. ``10.0.0.0/8,192.168.56.0/24``;
* ``SCAN_ALLOWED_DOMAINS`` – domain suffixes that may be scanned, e.g. ``lab.agh.edu.pl``.

When neither is set every target is allowed (development default). When a
list is set, targets outside it are rejected when they are saved and again by
the worker right before scanning. For domains the worker also resolves the
name and refuses to scan if any resolved address falls outside
``SCAN_ALLOWED_NETWORKS`` (protects against DNS pointing outside the lab).
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from typing import Any

from django.conf import settings

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


class OutOfScope(ValueError):
    """Target is outside the configured scan scope."""


def _split_setting(value: Any) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    return [str(item).strip() for item in (value or []) if str(item).strip()]


def allowed_networks() -> list[Network]:
    return [
        ipaddress.ip_network(item, strict=False)
        for item in _split_setting(getattr(settings, "SCAN_ALLOWED_NETWORKS", ""))
    ]


def allowed_domains() -> list[str]:
    return [
        item.lower().lstrip(".").rstrip(".")
        for item in _split_setting(getattr(settings, "SCAN_ALLOWED_DOMAINS", ""))
    ]


def scope_configured() -> bool:
    return bool(allowed_networks() or allowed_domains())


def _ip_allowed(address: ipaddress.IPv4Address | ipaddress.IPv6Address, networks: list[Network]) -> bool:
    return any(address.version == network.version and address in network for network in networks)


def _network_allowed(candidate: Network, networks: list[Network]) -> bool:
    return any(
        candidate.version == network.version and candidate.subnet_of(network)  # type: ignore[arg-type]
        for network in networks
    )


def _domain_allowed(domain: str, suffixes: list[str]) -> bool:
    return any(domain == suffix or domain.endswith("." + suffix) for suffix in suffixes)


def _resolve(domain: str, resolver: Callable[..., Any]) -> list[str]:
    try:
        infos = resolver(domain, None, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise OutOfScope(f"Could not resolve {domain} to check the scan scope.") from exc
    return sorted({info[4][0] for info in infos})


def check_target(
    address: str,
    target_type: str,
    *,
    resolve: bool = False,
    resolver: Callable[..., Any] = socket.getaddrinfo,
) -> None:
    """Raise :class:`OutOfScope` when the normalized target may not be scanned."""
    networks = allowed_networks()
    suffixes = allowed_domains()
    if not networks and not suffixes:
        return

    if target_type == "ip":
        if not _ip_allowed(ipaddress.ip_address(address), networks):
            raise OutOfScope(f"{address} is outside the allowed scan scope.")
        return

    if target_type == "cidr":
        if not _network_allowed(ipaddress.ip_network(address), networks):
            raise OutOfScope(f"{address} is outside the allowed scan scope.")
        return

    if target_type == "domain":
        if suffixes and not _domain_allowed(address, suffixes):
            raise OutOfScope(f"{address} is outside the allowed scan domains.")
        if not suffixes and not resolve:
            # Only networks are configured: the domain is checked by its addresses.
            # Saving is allowed; the worker resolves and checks before scanning.
            return
        if resolve and networks:
            resolved = _resolve(address, resolver)
            outside = [ip for ip in resolved if not _ip_allowed(ipaddress.ip_address(ip), networks)]
            if outside or not resolved:
                raise OutOfScope(
                    f"{address} resolves outside the allowed scan networks ({', '.join(outside) or 'no address'})."
                )
        return

    raise OutOfScope("Unsupported target type.")


def batch_prefix(version: int) -> int:
    if version == 4:
        return int(getattr(settings, "SCAN_BATCH_PREFIX_V4", 24))
    return int(getattr(settings, "SCAN_BATCH_PREFIX_V6", 120))


def split_into_batches(address: str, target_type: str) -> list[str]:
    """Split a CIDR larger than the batch prefix into equal sub-ranges (e.g. /16 -> 256 x /24).

    Small ranges, single IPs and domains are returned unchanged. Each batch is
    scanned and timed separately, so one slow subnet does not block the rest.
    """
    if target_type != "cidr":
        return [address]
    network = ipaddress.ip_network(address)
    prefix = batch_prefix(network.version)
    if network.prefixlen >= prefix:
        return [str(network)]
    return [str(subnet) for subnet in network.subnets(new_prefix=prefix)]
