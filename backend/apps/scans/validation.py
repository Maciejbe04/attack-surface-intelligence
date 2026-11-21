from __future__ import annotations

import ipaddress
import re


DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
MAX_CIDR_ADDRESSES = 4096


def normalize_target(address: str, target_type: str) -> str:
    if not isinstance(address, str):
        raise ValueError("Address must be a string.")
    address = address.strip()
    if not address or len(address) > 255:
        raise ValueError("Address is required and must not exceed 255 characters.")
    if any(character.isspace() or ord(character) < 32 for character in address):
        raise ValueError("Address contains invalid characters.")

    if target_type == "ip":
        try:
            return str(ipaddress.ip_address(address))
        except ValueError as exc:
            raise ValueError("Enter a valid IPv4 or IPv6 address.") from exc

    if target_type == "cidr":
        try:
            network = ipaddress.ip_network(address, strict=True)
        except ValueError as exc:
            raise ValueError("Enter a canonical IPv4 or IPv6 CIDR range.") from exc
        if network.num_addresses > MAX_CIDR_ADDRESSES:
            raise ValueError(
                f"CIDR ranges are limited to {MAX_CIDR_ADDRESSES} addresses."
            )
        return str(network)

    if target_type == "domain":
        candidate = address.rstrip(".")
        try:
            ascii_domain = candidate.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValueError("Enter a valid domain name.") from exc
        if len(ascii_domain) > 253 or "." not in ascii_domain:
            raise ValueError("Enter a fully qualified domain name.")
        labels = ascii_domain.split(".")
        if any(not DOMAIN_LABEL_RE.fullmatch(label) for label in labels):
            raise ValueError("Enter a valid domain name.")
        return ascii_domain

    raise ValueError("Unsupported target type.")
