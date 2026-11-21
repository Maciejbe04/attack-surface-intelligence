"""Analytical curiosity / priority highlights from normalized observations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .models import Observation, ScanRun

# Per-port curiosity in discovery style: high / medium / low / info.
# Explicit levels for known services; other open ports default to low.
CuriosityLevel = str  # "high" | "medium" | "low" | "info"

PORT_CURIOSITY_LEVEL: dict[int, CuriosityLevel] = {
    # high — remote access / cleartext / data stores
    21: "high",  # FTP
    22: "high",  # SSH
    23: "high",  # Telnet
    445: "high",  # SMB
    3389: "high",  # RDP
    5900: "high",  # VNC
    3306: "high",  # MySQL
    5432: "high",  # PostgreSQL
    6379: "high",  # Redis
    27017: "high",  # MongoDB
    1433: "high",  # MSSQL
    1521: "high",  # Oracle
    2375: "high",  # Docker API
    2376: "high",  # Docker TLS
    # medium — directory / mail / alternate HTTP
    25: "medium",  # SMTP
    110: "medium",  # POP3
    143: "medium",  # IMAP
    389: "medium",  # LDAP
    636: "medium",  # LDAPS
    8080: "medium",
    8443: "medium",
    9200: "medium",  # Elasticsearch
    11211: "medium",  # Memcached
    # info — common lower priority
    53: "info",  # DNS
    80: "info",  # HTTP
    443: "info",  # HTTPS
}

_CURIOSITY_RANK: dict[str, int] = {
    "high": 4,
    "medium": 3,
    "low": 2,
    "info": 1,
}

_LEGACY_NUMERIC_CURIOSITY: dict[int, CuriosityLevel] = {
    3: "high",
    2: "medium",
    1: "info",
}

_BORING_PORTS = {80, 443}
_INTERESTING_LEVELS = {"high", "medium"}
_INTERESTING_PORTS = {
    port
    for port, level in PORT_CURIOSITY_LEVEL.items()
    if level in _INTERESTING_LEVELS
}


def normalize_curiosity_level(value: Any) -> CuriosityLevel | None:
    """Normalize stored curiosity (string level or legacy 1–3) to a level label."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _LEGACY_NUMERIC_CURIOSITY.get(int(value))
    text = str(value).strip().lower()
    if text in _CURIOSITY_RANK:
        return text
    try:
        return _LEGACY_NUMERIC_CURIOSITY.get(int(text))
    except (TypeError, ValueError):
        return None


def curiosity_rank(level: CuriosityLevel | None) -> int:
    if not level:
        return 0
    return int(_CURIOSITY_RANK.get(level, 0))


def port_curiosity_score(port: int | None) -> CuriosityLevel | None:
    """Return high/medium/low/info for an open port number; None if port unknown."""
    if port is None:
        return None
    return PORT_CURIOSITY_LEVEL.get(int(port), "low")

_ABSENT = {
    Observation.Lifecycle.MISSING,
    Observation.Lifecycle.GONE,
}

_HINT_TOKENS = (
    "admin",
    "login",
    "signin",
    "sign-in",
    "staging",
    "stage.",
    "test.",
    "dev.",
    "wp-admin",
    "phpmyadmin",
    "manager",
    "console",
)


def _present(obs: Observation) -> bool:
    return obs.lifecycle not in _ABSENT


def _port_num(attrs: dict[str, Any]) -> int | None:
    raw = attrs.get("port")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _is_open_port(obs: Observation) -> bool:
    if obs.entity_type != Observation.EntityType.PORT or not _present(obs):
        return False
    state = str((obs.attrs or {}).get("state") or "open").lower()
    return state in {"open", "open|filtered", ""}


def _confidence_level(attrs: dict[str, Any]) -> str:
    level = str(attrs.get("level") or "").lower()
    if level in {"low", "medium", "high"}:
        return level
    conf = attrs.get("confidence")
    try:
        score = int(conf)
    except (TypeError, ValueError):
        return "low"
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _looks_like_admin_hint(obs: Observation) -> bool:
    if obs.entity_type not in {
        Observation.EntityType.HTTP,
        Observation.EntityType.SIGNATURE,
        Observation.EntityType.TECH,
    }:
        return False
    if not _present(obs):
        return False
    attrs = obs.attrs or {}
    blob = " ".join(
        str(attrs.get(key) or "")
        for key in ("url", "title", "endpoint", "technology", "path")
    ).lower()
    return any(token in blob for token in _HINT_TOKENS)


def _parse_not_after(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    # Accept ISO-ish and common TLS dump forms.
    candidates = [
        text,
        text.replace("Z", "+00:00"),
    ]
    for candidate in candidates:
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%b %d %H:%M:%S %Y %Z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text[:32], fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _cert_expiring(obs: Observation, *, within_days: int = 30) -> bool:
    if obs.entity_type != Observation.EntityType.CERT or not _present(obs):
        return False
    not_after = _parse_not_after(str((obs.attrs or {}).get("not_after") or ""))
    if not_after is None:
        return False
    now = datetime.now(timezone.utc)
    return now <= not_after <= now + timedelta(days=within_days)


def annotate_port_curiosity(run: ScanRun) -> int:
    """Write attrs.curiosity (high/medium/low/info) onto open port observations."""
    updated = 0
    for obs in run.observations.filter(entity_type=Observation.EntityType.PORT):
        if not _is_open_port(obs):
            attrs = dict(obs.attrs or {})
            if "curiosity" in attrs:
                attrs.pop("curiosity", None)
                obs.attrs = attrs
                obs.save(update_fields=("attrs", "updated_at"))
                updated += 1
            continue
        port = _port_num(obs.attrs or {})
        level = port_curiosity_score(port)
        attrs = dict(obs.attrs or {})
        if level is None:
            if "curiosity" in attrs:
                attrs.pop("curiosity", None)
                obs.attrs = attrs
                obs.save(update_fields=("attrs", "updated_at"))
                updated += 1
            continue
        if normalize_curiosity_level(attrs.get("curiosity")) == level:
            if attrs.get("curiosity") != level:
                attrs["curiosity"] = level
                obs.attrs = attrs
                obs.save(update_fields=("attrs", "updated_at"))
                updated += 1
            continue
        attrs["curiosity"] = level
        obs.attrs = attrs
        obs.save(update_fields=("attrs", "updated_at"))
        updated += 1
    return updated


def compute_curiosity_summary(run: ScanRun) -> dict[str, Any]:
    """Build curiosity counters + highlight sentences for a scan run."""
    annotate_port_curiosity(run)
    observations = list(run.observations.all())

    open_ports = [o for o in observations if _is_open_port(o)]
    hosts_with_open = sorted({o.target_address for o in open_ports if o.target_address})
    interesting_examples: list[dict[str, Any]] = []
    for obs in open_ports:
        port = _port_num(obs.attrs or {})
        level = port_curiosity_score(port)
        if port is None or level not in _INTERESTING_LEVELS:
            continue
        interesting_examples.append(
            {
                "address": obs.target_address,
                "port": port,
                "protocol": (obs.attrs or {}).get("protocol") or "tcp",
                "service": (obs.attrs or {}).get("service") or "",
                "curiosity": level,
                "sensitive": level == "high",
            }
        )
    interesting_examples.sort(
        key=lambda item: (
            -curiosity_rank(normalize_curiosity_level(item.get("curiosity"))),
            item.get("port") or 0,
        )
    )
    interesting_examples = interesting_examples[:8]

    admin_hints = [o for o in observations if _looks_like_admin_hint(o)]
    high_tech = [
        o
        for o in observations
        if o.entity_type
        in {Observation.EntityType.TECH, Observation.EntityType.SIGNATURE}
        and _present(o)
        and _confidence_level(o.attrs or {}) in {"medium", "high"}
    ]
    expiring = [o for o in observations if _cert_expiring(o)]

    service_counts: dict[str, int] = {}
    for obs in open_ports:
        service = str((obs.attrs or {}).get("service") or "").strip() or "unknown"
        service_counts[service] = service_counts.get(service, 0) + 1
    top_services = sorted(service_counts.items(), key=lambda item: (-item[1], item[0]))[:5]

    highlights: list[dict[str, Any]] = []

    def add_highlight(
        highlight_id: str,
        *,
        severity: str,
        text: str,
        count: int,
    ) -> None:
        if count <= 0:
            return
        highlights.append(
            {
                "id": highlight_id,
                "severity": severity,
                "text": text,
                "count": count,
            }
        )

    add_highlight(
        "hosts_with_open_ports",
        severity="info",
        text=f"{len(hosts_with_open)} host(s) have open ports",
        count=len(hosts_with_open),
    )
    add_highlight(
        "open_ports_total",
        severity="info",
        text=f"{len(open_ports)} open port(s) observed",
        count=len(open_ports),
    )
    add_highlight(
        "interesting_ports",
        severity="medium",
        text=f"{len(interesting_examples)} non-standard or sensitive port(s)",
        count=len(interesting_examples),
    )
    add_highlight(
        "admin_or_login_hints",
        severity="high",
        text=f"{len(admin_hints)} admin / login / staging hint(s)",
        count=len(admin_hints),
    )
    add_highlight(
        "high_confidence_tech",
        severity="medium",
        text=f"{len(high_tech)} medium/high-confidence technolog(ies)",
        count=len(high_tech),
    )
    add_highlight(
        "expiring_certs",
        severity="high",
        text=f"{len(expiring)} certificate(s) expire within 30 days",
        count=len(expiring),
    )

    return {
        "hosts_with_open_ports": len(hosts_with_open),
        "open_ports_total": len(open_ports),
        "interesting_ports": len(interesting_examples),
        "interesting_port_examples": interesting_examples,
        "admin_or_login_hints": len(admin_hints),
        "high_confidence_tech": len(high_tech),
        "expiring_certs": len(expiring),
        "top_services": [
            {"service": name, "count": count} for name, count in top_services
        ],
        "highlights": highlights[:6],
    }
