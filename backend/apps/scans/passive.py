"""Minimal passive discovery using Certificate Transparency and RDAP."""

from __future__ import annotations

import ipaddress
import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.core.cache import cache


CRT_SH_URL = "https://crt.sh/?q=%25.{query}&output=json"
RDAP_DOMAIN_URL = "https://rdap.org/domain/{query}"
RDAP_IP_URL = "https://rdap.org/ip/{query}"
CACHE_SECONDS = 15 * 60
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_SUBDOMAINS = 100
REQUEST_TIMEOUT_SECONDS = 8
_DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class PassiveDiscoveryInputError(ValueError):
    """Raised when a passive discovery query is not a valid IP or domain."""


class PassiveProviderError(RuntimeError):
    """Raised when a passive provider cannot return a usable response."""


def normalize_passive_query(raw: object) -> tuple[str, str]:
    value = str(raw or "").strip()
    if not value:
        raise PassiveDiscoveryInputError("query is required.")

    try:
        return "ip", str(ipaddress.ip_address(value))
    except ValueError:
        pass

    domain = value.rstrip(".").lower()
    try:
        domain = domain.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise PassiveDiscoveryInputError("query must be a valid IP or domain.") from exc

    if len(domain) > 253 or "." not in domain:
        raise PassiveDiscoveryInputError("query must be a valid IP or domain.")
    labels = domain.split(".")
    if any(not _DOMAIN_LABEL.fullmatch(label) for label in labels):
        raise PassiveDiscoveryInputError("query must be a valid IP or domain.")
    return "domain", domain


def _get_json(url: str) -> Any:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "SurfaceX/0.1 passive-discovery",
        },
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        raise PassiveProviderError(f"HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise PassiveProviderError("provider unavailable") from exc

    if len(raw) > MAX_RESPONSE_BYTES:
        raise PassiveProviderError("response exceeds 2 MiB limit")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PassiveProviderError("provider returned invalid JSON") from exc


def _normalize_certificate_name(value: object, root_domain: str) -> str | None:
    candidate = str(value or "").strip().lower().rstrip(".")
    if candidate.startswith("*."):
        candidate = candidate[2:]
    try:
        candidate = candidate.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    if candidate != root_domain and not candidate.endswith(f".{root_domain}"):
        return None
    try:
        kind, normalized = normalize_passive_query(candidate)
    except PassiveDiscoveryInputError:
        return None
    return normalized if kind == "domain" else None


def query_crt_sh(domain: str) -> list[str]:
    payload = _get_json(CRT_SH_URL.format(query=quote(domain, safe="")))
    if not isinstance(payload, list):
        raise PassiveProviderError("crt.sh returned an unexpected response")

    names: set[str] = set()
    for record in payload:
        if not isinstance(record, dict):
            continue
        for raw_name in str(record.get("name_value") or "").splitlines():
            normalized = _normalize_certificate_name(raw_name, domain)
            if normalized:
                names.add(normalized)
    return sorted(names)[:MAX_SUBDOMAINS]


def _vcard_name(entities: object) -> str:
    if not isinstance(entities, list):
        return ""
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        vcard = entity.get("vcardArray")
        if not isinstance(vcard, list) or len(vcard) != 2 or not isinstance(vcard[1], list):
            continue
        for field in vcard[1]:
            if (
                isinstance(field, list)
                and len(field) >= 4
                and field[0] in {"fn", "org"}
                and isinstance(field[3], str)
                and field[3].strip()
            ):
                return field[3].strip()[:300]
    return ""


def _rdap_asns(payload: dict[str, Any]) -> list[int]:
    candidates: list[object] = []
    for key in (
        "arin_originas0_originautnums",
        "originAutnums",
        "autnums",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    if payload.get("startAutnum") is not None:
        candidates.append(payload["startAutnum"])
    result: set[int] = set()
    for value in candidates:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            result.add(number)
    return sorted(result)


def summarize_rdap(payload: object, kind: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise PassiveProviderError("RDAP returned an unexpected response")
    nameservers = []
    for item in payload.get("nameservers") or []:
        if isinstance(item, dict) and item.get("ldhName"):
            nameservers.append(str(item["ldhName"]).lower())

    start = str(payload.get("startAddress") or "")
    end = str(payload.get("endAddress") or "")
    network = f"{start} – {end}" if start and end else start or end
    return {
        "handle": str(payload.get("handle") or "")[:300],
        "name": str(payload.get("name") or _vcard_name(payload.get("entities")) or "")[:300],
        "country": str(payload.get("country") or "")[:2].upper(),
        "network": network[:300],
        "asns": _rdap_asns(payload),
        "nameservers": sorted(set(nameservers))[:20] if kind == "domain" else [],
    }


def query_rdap(kind: str, query: str) -> dict[str, Any]:
    template = RDAP_IP_URL if kind == "ip" else RDAP_DOMAIN_URL
    payload = _get_json(template.format(query=quote(query, safe="")))
    return summarize_rdap(payload, kind)


def discover_passive(raw_query: object) -> dict[str, Any]:
    kind, query = normalize_passive_query(raw_query)
    cache_key = f"passive-discovery:v1:{kind}:{query}"
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return {**cached, "cached": True}

    subdomains: list[str] = []
    rdap: dict[str, Any] | None = None
    warnings: list[str] = []
    sources = {"crt_sh": "not_applicable", "rdap": "pending"}

    jobs = {"rdap": (query_rdap, (kind, query))}
    if kind == "domain":
        jobs["crt_sh"] = (query_crt_sh, (query,))
        sources["crt_sh"] = "pending"

    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        futures = {
            name: executor.submit(function, *args)
            for name, (function, args) in jobs.items()
        }
        for name, future in futures.items():
            try:
                value = future.result()
                if name == "crt_sh":
                    subdomains = value
                else:
                    rdap = value
                sources[name] = "ok"
            except PassiveProviderError as exc:
                sources[name] = "error"
                warnings.append(f"{name}: {exc}")
            except Exception:
                sources[name] = "error"
                warnings.append(f"{name}: provider unavailable")

    result = {
        "query": query,
        "type": kind,
        "subdomains": subdomains,
        "rdap": rdap,
        "sources": sources,
        "warnings": warnings,
        "cached": False,
    }
    cache.set(cache_key, result, CACHE_SECONDS)
    return result
