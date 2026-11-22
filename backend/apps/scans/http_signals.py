"""Extract interesting headers and cookies from an httpx record.

Pure, side-effect-free helpers used by normalize.py to enrich HTTP observations.
Cookie VALUES are never kept (they are session data); only names and flags.
Header values kept here are server/technology banners, not secrets.

httpx (-json -include-response-header) returns headers as a dict with
lowercased, underscore-separated names, e.g. "x_powered_by", "set_cookie".
"""

from __future__ import annotations

from typing import Any

# Headers that leak technology / version / internal routing (useful fingerprinting signal).
INFO_LEAK_HEADERS = {
    "server": "Server",
    "x_powered_by": "X-Powered-By",
    "x_aspnet_version": "X-AspNet-Version",
    "x_aspnetmvc_version": "X-AspNetMvc-Version",
    "x_generator": "X-Generator",
    "x_drupal_cache": "X-Drupal-Cache",
    "x_runtime": "X-Runtime",
    "via": "Via",
    "x_served_by": "X-Served-By",
    "x_backend_server": "X-Backend-Server",
    "x_debug_token": "X-Debug-Token",
}

# Security headers whose PRESENCE is good and whose ABSENCE is worth flagging.
SECURITY_HEADERS = {
    "strict_transport_security": "Strict-Transport-Security",
    "content_security_policy": "Content-Security-Policy",
    "x_frame_options": "X-Frame-Options",
    "x_content_type_options": "X-Content-Type-Options",
}

# Ubiquitous, uninteresting headers every server sends — skipped as noise.
BORING_HEADERS = {
    "date", "content_type", "content_length", "content_encoding", "content_language",
    "connection", "keep_alive", "transfer_encoding", "accept_ranges", "vary",
    "cache_control", "expires", "pragma", "etag", "last_modified", "age", "upgrade",
    "content_range", "set_cookie", "accept", "x_content_type_options",
    "strict_transport_security", "content_security_policy", "x_frame_options",
    "referrer_policy", "permissions_policy",
}


def _display_header(key: str) -> str:
    return "-".join(part.upper() if part in {"id", "ip", "ua", "ssl", "xss", "ok"} else part.capitalize()
                    for part in key.split("_"))


# Cookie name (lowercased) -> technology it reveals.
COOKIE_TECH = {
    "phpsessid": "PHP",
    "jsessionid": "Java",
    "asp.net_sessionid": "ASP.NET",
    "aspnet_sessionid": "ASP.NET",
    "aspnetcore": "ASP.NET Core",
    "laravel_session": "Laravel",
    "ci_session": "CodeIgniter",
    "connect.sid": "Express / Node.js",
    "csrftoken": "Django",
    "sessionid": "Django",
    "_rails": "Ruby on Rails",
    "symfony": "Symfony",
}
COOKIE_TECH_PREFIX = {
    "wordpress_": "WordPress",
    "wp-settings": "WordPress",
    "woocommerce_": "WooCommerce",
}

MAX_HEADER_VALUE = 200
MAX_COOKIES = 25


def _headers(record: dict[str, Any]) -> dict[str, str]:
    raw = record.get("header") or record.get("headers") or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        name = str(key).strip().lower().replace("-", "_")
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        out[name] = str(value)
    return out


def _cookie_lines(headers: dict[str, str], record: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    raw = headers.get("set_cookie", "")
    if raw:
        lines.extend(part for part in raw.replace("\r", "\n").split("\n") if part.strip())
    extra = record.get("cookies") or record.get("cookie")
    if isinstance(extra, list):
        lines.extend(str(item) for item in extra if item)
    elif isinstance(extra, str) and extra:
        lines.append(extra)
    return lines


def _parse_cookie(line: str) -> dict[str, Any] | None:
    parts = [p.strip() for p in line.split(";") if p.strip()]
    if not parts or "=" not in parts[0]:
        return None
    name = parts[0].split("=", 1)[0].strip()[:120]
    if not name:
        return None
    attrs = {p.split("=", 1)[0].strip().lower(): p for p in parts[1:]}
    samesite = ""
    if "samesite" in attrs and "=" in attrs["samesite"]:
        samesite = attrs["samesite"].split("=", 1)[1].strip()
    return {
        "name": name,  # name only — value is never stored
        "httponly": "httponly" in attrs,
        "secure": "secure" in attrs,
        "samesite": samesite,
    }


def _cookie_tech(name: str) -> str | None:
    low = name.lower()
    if low in COOKIE_TECH:
        return COOKIE_TECH[low]
    for prefix, tech in COOKIE_TECH_PREFIX.items():
        if low.startswith(prefix):
            return tech
    return None


def extract_http_signals(record: dict[str, Any], *, is_https: bool = False) -> dict[str, Any]:
    """Return attrs describing interesting headers and cookies for one HTTP endpoint."""
    headers = _headers(record)
    signals: dict[str, Any] = {}
    if not headers and not record.get("cookies"):
        return signals

    # Capture every non-standard header (name -> value); the boring ubiquitous
    # ones and the security headers are handled separately.
    interesting = {
        _display_header(key): value[:MAX_HEADER_VALUE]
        for key, value in headers.items()
        if key not in BORING_HEADERS and value
    }
    if interesting:
        signals["interesting_headers"] = interesting

    missing = [label for key, label in SECURITY_HEADERS.items() if not headers.get(key)]
    present = [label for key, label in SECURITY_HEADERS.items() if headers.get(key)]
    if present:
        signals["security_headers_present"] = present
    if missing:
        signals["security_headers_missing"] = missing

    cookies: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in _cookie_lines(headers, record):
        parsed = _parse_cookie(line)
        if parsed and parsed["name"].lower() not in seen:
            seen.add(parsed["name"].lower())
            cookies.append(parsed)
        if len(cookies) >= MAX_COOKIES:
            break
    if cookies:
        signals["cookies"] = cookies
        signals["cookie_names"] = [c["name"] for c in cookies]
        tech = sorted({t for c in cookies if (t := _cookie_tech(c["name"]))})
        if tech:
            signals["cookie_tech"] = tech
        insecure = [
            c["name"]
            for c in cookies
            if not c["httponly"] or (is_https and not c["secure"]) or not c["samesite"]
        ]
        if insecure:
            signals["insecure_cookies"] = insecure

    # Flat one-line summaries (safe to show in a table cell).
    header_bits = [f"{k}: {v}" for k, v in list((signals.get("interesting_headers") or {}).items())[:6]]
    if signals.get("security_headers_missing"):
        header_bits.append("no " + ", ".join(signals["security_headers_missing"][:3]))
    if header_bits:
        signals["headers_summary"] = " · ".join(header_bits)[:300]
    if signals.get("cookies"):
        parts = []
        for c in signals["cookies"]:
            tech = _cookie_tech(c["name"])
            flag = "" if (c["httponly"] and c["secure"]) else " (insecure)"
            parts.append(c["name"] + (f" [{tech}]" if tech else "") + flag)
        signals["cookies_summary"] = ", ".join(parts)[:300]

    return signals


def interesting_header_count(attrs: dict[str, Any]) -> int:
    return len(attrs.get("interesting_headers") or {}) + len(attrs.get("security_headers_missing") or [])
