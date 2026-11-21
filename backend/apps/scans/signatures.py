"""Declarative YAML signature engine (header/cookie/html/path/status/versionRegex)."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

def _signatures_root() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "signatures",  # repo root when backend/ is under project
        here.parents[2].parent / "signatures",  # /app/signatures next to /app/backend
        Path("/app/signatures"),
    ]
    for path in candidates:
        if path.is_dir():
            return path
    return candidates[0]


SIGNATURES_ROOT = _signatures_root()
PACK_VERSION = "1.0.0"
MAX_BODY = 64 * 1024
MAX_REGEX_LEN = 200
MAX_REGEX_INPUT = 32 * 1024


def _safe_re(pattern: str, text: str) -> re.Match[str] | None:
    if not pattern or len(pattern) > MAX_REGEX_LEN:
        return None
    sample = text[:MAX_REGEX_INPUT]
    try:
        return re.search(pattern, sample, flags=re.IGNORECASE | re.DOTALL)
    except re.error:
        return None


def _headers_map(record: dict[str, Any]) -> dict[str, str]:
    raw = record.get("header") or record.get("headers") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(k).lower(): str(v) for k, v in raw.items()}


def _cookie_names(record: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    cookies = record.get("cookies") or record.get("cookie")
    if isinstance(cookies, list):
        for item in cookies:
            if isinstance(item, dict) and item.get("name"):
                names.add(str(item["name"]).lower())
            elif isinstance(item, str) and item:
                names.add(item.split("=", 1)[0].strip().lower())
    elif isinstance(cookies, dict):
        names.update(str(k).lower() for k in cookies)
    elif isinstance(cookies, str):
        for part in cookies.split(";"):
            name = part.split("=", 1)[0].strip().lower()
            if name:
                names.add(name)
    # Set-Cookie often lives in headers.
    headers = _headers_map(record)
    set_cookie = headers.get("set-cookie", "")
    if set_cookie:
        for part in set_cookie.split(","):
            name = part.split("=", 1)[0].strip().lower()
            if name and " " not in name:
                names.add(name)
    return names


def _html_body(record: dict[str, Any]) -> str:
    for key in ("body", "raw_body", "html", "response_body"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value[:MAX_BODY]
    return ""


def _match_rule(rule: dict[str, Any], record: dict[str, Any]) -> tuple[bool, str]:
    rtype = str(rule.get("type") or "")
    headers = _headers_map(record)
    if rtype == "header":
        name = str(rule.get("name") or "").lower()
        value = headers.get(name, "")
        if "equals" in rule:
            return value.lower() == str(rule["equals"]).lower(), f"header:{name}"
        if "contains" in rule:
            return str(rule["contains"]).lower() in value.lower(), f"header:{name}"
        if "regex" in rule:
            return bool(_safe_re(str(rule["regex"]), value)), f"header:{name}"
        return bool(value), f"header:{name}"
    if rtype == "cookie":
        name = str(rule.get("name") or "").lower()
        return name in _cookie_names(record), f"cookie:{name}"
    if rtype == "html":
        body = _html_body(record)
        if "contains" in rule:
            return str(rule["contains"]).lower() in body.lower(), "html"
        if "regex" in rule:
            return bool(_safe_re(str(rule["regex"]), body)), "html"
        return False, "html"
    if rtype == "favicon":
        expected = str(rule.get("hash") or "")
        actual = str(record.get("favicon") or record.get("favicon-hash") or "")
        return bool(expected) and expected == actual, "favicon"
    if rtype == "path":
        path = str(rule.get("path") or "")
        if not path.startswith("/") or "://" in path or "//" in path[1:]:
            return False, "path"
        # Path probes are optional; match when URL path equals or record notes it.
        url = str(record.get("url") or record.get("input") or "")
        status_codes = rule.get("status") or []
        status_code = record.get("status_code") or record.get("status-code")
        path_ok = path in url or url.rstrip("/").endswith(path.rstrip("/"))
        if not path_ok:
            # Soft match: if the record itself is for that path endpoint.
            return False, f"path:{path}"
        if status_codes and status_code not in status_codes:
            return False, f"path:{path}"
        return True, f"path:{path}"
    if rtype == "versionRegex":
        source = str(rule.get("source") or "html")
        text = _html_body(record) if source == "html" else str(
            _headers_map(record).get(source, "")
        )
        match = _safe_re(str(rule.get("pattern") or ""), text)
        if match:
            return True, match.group(1) if match.lastindex else match.group(0)
        return False, "version"
    if rtype == "status":
        codes = rule.get("status") or rule.get("codes") or []
        status_code = record.get("status_code") or record.get("status-code")
        return status_code in codes, "status"
    return False, rtype


def _confidence_level(score: int, bands: dict[str, Any]) -> str:
    for level in ("high", "medium", "low"):
        band = bands.get(level) if isinstance(bands, dict) else None
        if isinstance(band, list) and len(band) == 2:
            lo, hi = int(band[0]), int(band[1])
            if lo <= score <= hi:
                return level
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def evaluate_signature(sig: dict[str, Any], record: dict[str, Any]) -> dict[str, Any] | None:
    meta = sig.get("metadata") or {}
    spec = sig.get("spec") or {}
    rules = spec.get("rules") if isinstance(spec.get("rules"), list) else []
    match_any = bool(spec.get("matchAny"))
    score = 0
    evidence: list[str] = []
    version = ""
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        ok, detail = _match_rule(rule, record)
        if not ok:
            if not match_any:
                continue
            continue
        weight = int(rule.get("weight") or 10)
        score += weight
        evidence.append(f"{rule.get('type')}:{detail}")
        if rule.get("type") == "versionRegex" and detail and detail != "version":
            version = str(detail)[:64]
        if match_any:
            break
    score = min(100, score)
    if score <= 0:
        return None
    level = _confidence_level(score, spec.get("confidence") or {})
    return {
        "signature_id": str(meta.get("id") or "")[:100],
        "technology": str(meta.get("name") or meta.get("id") or "")[:200],
        "category": str(meta.get("category") or "")[:64],
        "endpoint": str(record.get("url") or record.get("input") or "")[:500],
        "confidence": score,
        "level": level,
        "version": version,
        "evidence": "; ".join(evidence)[:500],
        "signature_version": int(meta.get("version") or 1),
    }


@lru_cache(maxsize=1)
def load_signatures() -> tuple[dict[str, Any], ...]:
    root = SIGNATURES_ROOT
    if not root.is_dir():
        return tuple()
    loaded: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and data.get("kind") == "Signature":
            loaded.append(data)
    return tuple(loaded)


def pack_info() -> dict[str, Any]:
    sigs = load_signatures()
    return {
        "version": PACK_VERSION,
        "count": len(sigs),
        "ids": [str((s.get("metadata") or {}).get("id") or "") for s in sigs],
    }


def match_http_records(http_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signatures = load_signatures()
    findings: list[dict[str, Any]] = []
    for record in http_records:
        if not isinstance(record, dict):
            continue
        for sig in signatures:
            hit = evaluate_signature(sig, record)
            if hit:
                findings.append(hit)
            if len(findings) >= 2000:
                return findings
    return findings
