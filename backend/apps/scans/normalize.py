"""Normalize ScanBatch.result into Observation rows and compute lifecycle."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from .crypto import seal, seal_json
from .curiosity import compute_curiosity_summary, port_curiosity_score
from .models import FingerprintEvidence, Observation, ScanBatch, ScanRun


def _attr_fingerprint(attrs: dict[str, Any]) -> str:
    import json

    return json.dumps(attrs, sort_keys=True, separators=(",", ":"), default=str)


def extract_observation_rows(
    batch: ScanBatch,
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build observation dicts from a worker result payload."""
    rows: list[dict[str, Any]] = []
    address = batch.target_address
    target = batch.target

    hosts = result.get("hosts") if isinstance(result.get("hosts"), list) else []
    for host in hosts:
        if not isinstance(host, dict):
            continue
        host_addr = str(host.get("address") or address)[:255]
        host_key = f"host:{host_addr}"
        host_attrs = {
            "address": host_addr,
            "status": host.get("status") or host.get("state") or "up",
        }
        rows.append(
            {
                "entity_type": Observation.EntityType.HOST,
                "entity_key": host_key,
                "target_address": host_addr,
                "target": target,
                "attrs": host_attrs,
                "evidence": [
                    {
                        "kind": "host",
                        "summary": f"Host {host_addr} observed",
                        "payload": host,
                    }
                ],
            }
        )
        ports = host.get("ports") if isinstance(host.get("ports"), list) else []
        for port in ports:
            if not isinstance(port, dict):
                continue
            port_num = port.get("port") or port.get("portid")
            proto = port.get("protocol") or port.get("protocol", "tcp")
            if port_num is None:
                continue
            key = f"port:{host_addr}:{proto}/{port_num}"
            port_int = int(port_num) if str(port_num).isdigit() else port_num
            state = port.get("state") or port.get("status") or "open"
            attrs = {
                "address": host_addr,
                "port": port_int,
                "protocol": proto,
                "state": state,
                "service": port.get("service") or port.get("name") or "",
                "product": port.get("product") or "",
                "version": port.get("version") or "",
            }
            if str(state).lower() in {"open", "open|filtered", ""}:
                try:
                    score = port_curiosity_score(int(port_int))
                except (TypeError, ValueError):
                    score = None
                if score is not None:
                    attrs["curiosity"] = score
            rows.append(
                {
                    "entity_type": Observation.EntityType.PORT,
                    "entity_key": key,
                    "target_address": host_addr,
                    "target": target,
                    "attrs": attrs,
                    "evidence": [
                        {
                            "kind": "port",
                            "summary": f"{proto}/{port_num} {attrs['service']}".strip(),
                            "payload": port,
                        }
                    ],
                }
            )

    http_records = result.get("http") if isinstance(result.get("http"), list) else []
    for record in http_records:
        if not isinstance(record, dict):
            continue
        url = str(record.get("url") or record.get("input") or "")[:500]
        if not url:
            continue
        status_code = record.get("status_code") or record.get("status-code")
        title = str(record.get("title") or "")[:300]
        server = str(record.get("webserver") or record.get("server") or "")[:200]
        http_key = f"http:{url}"
        http_attrs = {
            "url": url,
            "status_code": status_code,
            "title": title,
            "server": server,
        }
        rows.append(
            {
                "entity_type": Observation.EntityType.HTTP,
                "entity_key": http_key,
                "target_address": address,
                "target": target,
                "attrs": http_attrs,
                "evidence": [
                    {
                        "kind": "http",
                        "summary": f"{status_code or '?'} {url}",
                        "payload": {
                            "url": url,
                            "status_code": status_code,
                            "title": title,
                            "server": server,
                            "tech": record.get("tech"),
                        },
                    }
                ],
            }
        )
        techs = record.get("tech") if isinstance(record.get("tech"), list) else []
        for tech in techs[:30]:
            if not isinstance(tech, str) or not tech.strip():
                continue
            tech_name = tech.strip()[:200]
            tech_key = f"tech:{url}:{tech_name.lower()}"
            rows.append(
                {
                    "entity_type": Observation.EntityType.TECH,
                    "entity_key": tech_key,
                    "target_address": address,
                    "target": target,
                    "attrs": {"url": url, "technology": tech_name, "confidence": 30},
                    "evidence": [
                        {
                            "kind": "tech",
                            "summary": f"{tech_name} via httpx",
                            "payload": {"technology": tech_name, "url": url},
                        }
                    ],
                }
            )
        tls = record.get("tls") or record.get("tls-grab") or record.get("cert")
        if isinstance(tls, dict) and tls:
            subject = str(
                tls.get("subject_cn")
                or tls.get("subject_cn")
                or tls.get("subject")
                or ""
            )[:300]
            issuer = str(tls.get("issuer_cn") or tls.get("issuer") or "")[:300]
            cert_key = f"cert:{url}:{subject or 'unknown'}"
            rows.append(
                {
                    "entity_type": Observation.EntityType.CERT,
                    "entity_key": cert_key,
                    "target_address": address,
                    "target": target,
                    "attrs": {
                        "url": url,
                        "subject": subject,
                        "issuer": issuer,
                        "not_after": str(tls.get("not_after") or tls.get("expires") or ""),
                    },
                    "evidence": [
                        {
                            "kind": "cert",
                            "summary": f"TLS {subject or url}",
                            "payload": tls,
                        }
                    ],
                }
            )

    signatures = result.get("signatures") if isinstance(result.get("signatures"), list) else []
    for finding in signatures:
        if not isinstance(finding, dict):
            continue
        tech = str(finding.get("technology") or finding.get("id") or "")[:200]
        endpoint = str(finding.get("endpoint") or "")[:500]
        if not tech:
            continue
        conf = finding.get("confidence")
        level = str(finding.get("level") or "low")[:16]
        sig_key = f"signature:{endpoint}:{tech.lower()}"
        rows.append(
            {
                "entity_type": Observation.EntityType.SIGNATURE,
                "entity_key": sig_key,
                "target_address": address,
                "target": target,
                "attrs": {
                    "technology": tech,
                    "endpoint": endpoint,
                    "confidence": conf,
                    "level": level,
                },
                "evidence": [
                    {
                        "kind": "signature",
                        "summary": f"{tech} ({level})",
                        "payload": finding,
                    }
                ],
            }
        )

    return rows


def _run_target_addresses(run: ScanRun) -> set[str]:
    return {batch.target_address for batch in run.batches.all() if batch.target_address}


def same_scan_scope(current: ScanRun, other: ScanRun) -> bool:
    """True when both runs cover the same group or the same host/target set."""
    if current.group_id or other.group_id:
        return bool(current.group_id) and current.group_id == other.group_id
    return _run_target_addresses(current) == _run_target_addresses(other) and bool(
        _run_target_addresses(current)
    )


def previous_completed_run(run: ScanRun) -> ScanRun | None:
    qs = (
        ScanRun.objects.filter(
            owner_id=run.owner_id,
            status=ScanRun.Status.COMPLETED,
            finished_at__isnull=False,
        )
        .exclude(pk=run.pk)
        .prefetch_related("batches")
    )
    if run.group_id:
        qs = qs.filter(group_id=run.group_id)
        return qs.order_by("-finished_at", "-id").first()

    current_targets = _run_target_addresses(run)
    if not current_targets:
        return None
    # Host / ad-hoc scans: only previous runs with the exact same target set.
    for candidate in qs.filter(group_id__isnull=True).order_by("-finished_at", "-id")[:50]:
        if _run_target_addresses(candidate) == current_targets:
            return candidate
    return None


def _previous_map(prev: ScanRun | None) -> dict[str, Observation]:
    if prev is None:
        return {}
    return {obs.entity_key: obs for obs in prev.observations.all()}


@transaction.atomic
def persist_batch_observations(batch: ScanBatch) -> int:
    """Create observations for one completed batch (lifecycle provisional NEW)."""
    result = batch.result if isinstance(batch.result, dict) else {}
    rows = extract_observation_rows(batch, result)
    created = 0
    for row in rows:
        obs, was_created = Observation.objects.update_or_create(
            run=batch.run,
            entity_key=row["entity_key"],
            defaults={
                "target": row.get("target"),
                "target_address": row["target_address"],
                "entity_type": row["entity_type"],
                "lifecycle": Observation.Lifecycle.NEW,
                "attrs": row["attrs"],
                "source": Observation.Source.SCANNER,
                "miss_streak": 0,
            },
        )
        if was_created:
            created += 1
        obs.evidence.all().delete()
        for ev in row.get("evidence") or []:
            payload = ev.get("payload")
            ciphertext = ""
            if isinstance(payload, dict):
                ciphertext = seal_json(payload)
            elif isinstance(payload, str):
                ciphertext = seal(payload)
            FingerprintEvidence.objects.create(
                observation=obs,
                kind=str(ev.get("kind") or "summary")[:32],
                summary=str(ev.get("summary") or "")[:500],
                ciphertext=ciphertext,
                meta={"encrypted": bool(ciphertext)},
            )
    return created


@transaction.atomic
def finalize_run_lifecycle(run: ScanRun) -> dict[str, int]:
    """
    After a run becomes terminal (completed/partial), set lifecycle vs previous
    completed run and emit MISSING/GONE for keys that disappeared.
    Partial/failed still get NEW/CHANGED for present keys; MISSING/GONE only when
    the run status is COMPLETED (full measurement).
    """
    prev = previous_completed_run(run)
    prev_map = _previous_map(prev)
    current = list(run.observations.all())
    current_keys = {obs.entity_key for obs in current}
    counts = {
        "NEW": 0,
        "CHANGED": 0,
        "UNCHANGED": 0,
        "MISSING": 0,
        "GONE": 0,
        "FLAKY": 0,
    }

    for obs in current:
        old = prev_map.get(obs.entity_key)
        if old is None:
            obs.lifecycle = Observation.Lifecycle.NEW
            obs.miss_streak = 0
        elif _attr_fingerprint(old.attrs) != _attr_fingerprint(obs.attrs):
            obs.lifecycle = Observation.Lifecycle.CHANGED
            obs.miss_streak = 0
        else:
            # Carry forward flaky/gone recovery as UNCHANGED when present again.
            if old.lifecycle in {
                Observation.Lifecycle.MISSING,
                Observation.Lifecycle.FLAKY,
                Observation.Lifecycle.GONE,
            }:
                obs.lifecycle = Observation.Lifecycle.FLAKY
            else:
                obs.lifecycle = Observation.Lifecycle.UNCHANGED
            obs.miss_streak = 0
        obs.save(update_fields=("lifecycle", "miss_streak", "updated_at"))
        counts[obs.lifecycle] = counts.get(obs.lifecycle, 0) + 1

    if run.status == ScanRun.Status.COMPLETED and prev is not None:
        for key, old in prev_map.items():
            if key in current_keys:
                continue
            streak = old.miss_streak + 1
            if streak >= 3:
                lifecycle = Observation.Lifecycle.GONE
            elif streak == 2:
                lifecycle = Observation.Lifecycle.FLAKY
            else:
                lifecycle = Observation.Lifecycle.MISSING
            Observation.objects.create(
                run=run,
                target=old.target,
                target_address=old.target_address,
                entity_type=old.entity_type,
                entity_key=key,
                lifecycle=lifecycle,
                attrs=old.attrs,
                source=Observation.Source.SCANNER,
                miss_streak=streak,
            )
            counts[lifecycle] = counts.get(lifecycle, 0) + 1

    summary = dict(run.result_summary or {})
    summary["lifecycle"] = counts
    summary["curiosity"] = compute_curiosity_summary(run)
    run.result_summary = summary
    run.save(update_fields=("result_summary", "updated_at"))
    return counts


def diff_runs(current: ScanRun, against: ScanRun) -> dict[str, Any]:
    cur_map = {o.entity_key: o for o in current.observations.all()}
    old_map = {o.entity_key: o for o in against.observations.all()}
    added = []
    removed = []
    changed = []
    for key, obs in cur_map.items():
        if key not in old_map:
            added.append(_obs_payload(obs))
        elif _attr_fingerprint(old_map[key].attrs) != _attr_fingerprint(obs.attrs):
            changed.append(
                {
                    "entity_key": key,
                    "before": old_map[key].attrs,
                    "after": obs.attrs,
                    "lifecycle": obs.lifecycle,
                }
            )
    for key, obs in old_map.items():
        if key not in cur_map:
            removed.append(_obs_payload(obs))
    return {
        "current_run_id": current.pk,
        "against_run_id": against.pk,
        "added": added,
        "removed": removed,
        "changed": changed,
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
        },
    }


def _obs_payload(obs: Observation) -> dict[str, Any]:
    return {
        "id": obs.pk,
        "entity_type": obs.entity_type,
        "entity_key": obs.entity_key,
        "lifecycle": obs.lifecycle,
        "target_address": obs.target_address,
        "attrs": obs.attrs,
        "miss_streak": obs.miss_streak,
    }
