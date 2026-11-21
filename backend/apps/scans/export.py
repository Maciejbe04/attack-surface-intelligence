"""CSV/JSON export of normalized observations (surfacex.export.v1)."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from django.utils import timezone

from .models import Observation, ScanRun
from .normalize import _obs_payload


SCHEMA = "surfacex.export.v1"


def build_export_payload(run: ScanRun) -> dict[str, Any]:
    observations = [
        {
            **_obs_payload(obs),
            "source": obs.source,
        }
        for obs in run.observations.all()
    ]
    return {
        "schema": SCHEMA,
        "exported_at": timezone.now().isoformat(),
        "run": {
            "id": run.pk,
            "status": run.status,
            "group_id": run.group_id,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "modules": run.modules_snapshot,
            "result_summary": run.result_summary,
        },
        "observations": observations,
    }


def export_json_bytes(run: ScanRun) -> bytes:
    return json.dumps(
        build_export_payload(run),
        indent=2,
        ensure_ascii=False,
    ).encode("utf-8")


def export_csv_bytes(run: ScanRun) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "entity_type",
            "entity_key",
            "lifecycle",
            "target_address",
            "source",
            "miss_streak",
            "attrs_json",
        ],
    )
    writer.writeheader()
    for obs in run.observations.all():
        writer.writerow(
            {
                "entity_type": obs.entity_type,
                "entity_key": obs.entity_key,
                "lifecycle": obs.lifecycle,
                "target_address": obs.target_address,
                "source": obs.source,
                "miss_streak": obs.miss_streak,
                "attrs_json": json.dumps(obs.attrs, ensure_ascii=False, separators=(",", ":")),
            }
        )
    return buffer.getvalue().encode("utf-8")


def import_observations_payload(
    *,
    run: ScanRun,
    observations: list[dict[str, Any]],
) -> int:
    """Import observation dicts onto a run (source=import)."""
    created = 0
    for item in observations:
        if not isinstance(item, dict):
            continue
        entity_key = str(item.get("entity_key") or "")[:512]
        entity_type = str(item.get("entity_type") or Observation.EntityType.HOST)[:16]
        if not entity_key:
            continue
        attrs = item.get("attrs") if isinstance(item.get("attrs"), dict) else {}
        _, was_created = Observation.objects.update_or_create(
            run=run,
            entity_key=entity_key,
            defaults={
                "target_address": str(item.get("target_address") or "")[:255],
                "entity_type": entity_type,
                "lifecycle": str(item.get("lifecycle") or Observation.Lifecycle.NEW)[:16],
                "attrs": attrs,
                "source": Observation.Source.IMPORT,
                "miss_streak": int(item.get("miss_streak") or 0),
            },
        )
        if was_created:
            created += 1
    return created
