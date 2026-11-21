from __future__ import annotations

from .models import ScanBatch, ScanEvent, ScanRun

MAX_EVENTS_PER_RUN = 1000


def append_scan_event(
    run: ScanRun,
    message: str,
    *,
    level: str = ScanEvent.Level.INFO,
    batch: ScanBatch | None = None,
    source: str = "api",
) -> ScanEvent | None:
    text = message.strip()
    if not text:
        return None
    if ScanEvent.objects.filter(run_id=run.pk).count() >= MAX_EVENTS_PER_RUN:
        return None
    return ScanEvent.objects.create(
        run=run,
        batch=batch,
        level=level if level in ScanEvent.Level.values else ScanEvent.Level.INFO,
        source=source[:32],
        message=text[:2000],
    )
