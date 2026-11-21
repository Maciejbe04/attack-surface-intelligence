"""Scan queueing shared by the public API, group scans and the group scheduler."""

from __future__ import annotations

from datetime import timedelta
from functools import partial

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone

from .events import append_scan_event
from .models import GroupSchedule, ScanBatch, ScanRun, Target, TargetGroup
from .tasks import execute_batch


def publish_batch(batch_id: int, delivery_id: str) -> None:
    try:
        execute_batch.apply_async(
            args=(batch_id, delivery_id),
            queue="scan",
        )
    except Exception as exc:
        # PostgreSQL remains authoritative when the broker is unavailable.
        with transaction.atomic():
            batch = (
                ScanBatch.objects.select_for_update()
                .select_related("run")
                .get(pk=batch_id, delivery_id=delivery_id)
            )
            if batch.status != ScanBatch.Status.QUEUED:
                return
            batch.status = ScanBatch.Status.FAILED
            batch.error = f"Queue publish failed: {type(exc).__name__}"
            batch.finished_at = timezone.now()
            batch.save(
                update_fields=("status", "error", "finished_at", "updated_at")
            )
            run = ScanRun.objects.select_for_update().get(pk=batch.run_id)
            run.failed_batches = run.batches.filter(
                status=ScanBatch.Status.FAILED
            ).count()
            unfinished = run.batches.filter(
                status__in=(ScanBatch.Status.QUEUED, ScanBatch.Status.RUNNING)
            ).exists()
            if not unfinished:
                run.status = ScanRun.Status.FAILED
                run.finished_at = timezone.now()
            run.result_summary = {
                "completed": run.completed_batches,
                "failed": run.failed_batches,
                "cancelled": run.batches.filter(
                    status=ScanBatch.Status.CANCELLED
                ).count(),
            }
            run.save(
                update_fields=(
                    "status",
                    "failed_batches",
                    "result_summary",
                    "finished_at",
                    "updated_at",
                )
            )


def queue_scan_for_targets(
    *,
    owner: User,
    targets: list[Target],
    modules: list[dict],
    client_request_id: str = "",
    group: TargetGroup | None = None,
    schedule: GroupSchedule | None = None,
    window_seconds: int | None = None,
) -> tuple[ScanRun, bool]:
    """Create a scan run for targets. Returns (run, created)."""
    if not targets:
        raise ValueError("At least one target is required.")

    with transaction.atomic():
        if client_request_id:
            existing = (
                ScanRun.objects.select_for_update()
                .filter(owner=owner, client_request_id=client_request_id)
                .first()
            )
            if existing is not None:
                return existing, False

        deadline_at = None
        if window_seconds and window_seconds > 0:
            deadline_at = timezone.now() + timedelta(seconds=window_seconds)

        try:
            with transaction.atomic():
                run = ScanRun.objects.create(
                    owner=owner,
                    modules_snapshot=modules,
                    client_request_id=client_request_id,
                    total_batches=len(targets),
                    group=group,
                    schedule=schedule,
                    window_seconds=window_seconds if window_seconds else None,
                    deadline_at=deadline_at,
                )
        except IntegrityError:
            run = ScanRun.objects.get(
                owner=owner,
                client_request_id=client_request_id,
            )
            return run, False

        batches = ScanBatch.objects.bulk_create(
            [
                ScanBatch(
                    run=run,
                    target=target,
                    target_address=target.address,
                    target_type=target.target_type,
                )
                for target in targets
            ]
        )
        for batch in batches:
            transaction.on_commit(
                partial(publish_batch, batch.pk, str(batch.delivery_id))
            )

        module_ids = [
            module.get("id", "?")
            for module in modules
            if isinstance(module, dict)
        ]
        if schedule is not None:
            origin = f" by schedule of group '{group.name if group else schedule.group_id}'"
        elif group is not None:
            origin = f" for group '{group.name}'"
        else:
            origin = ""
        append_scan_event(
            run,
            (
                f"Queued scan #{run.pk}{origin} for {len(batches)} target(s); "
                f"modules: {', '.join(str(item) for item in module_ids) or 'none'}."
            ),
            source="api",
        )
        if len(batches) <= 50:
            for batch in batches:
                append_scan_event(
                    run,
                    f"Batch queued for {batch.target_address} ({batch.target_type}).",
                    batch=batch,
                    source="api",
                )
        else:
            append_scan_event(
                run,
                (
                    f"Queued {len(batches)} batches "
                    "(individual host lines omitted for large imports)."
                ),
                source="api",
            )
    return run, True
