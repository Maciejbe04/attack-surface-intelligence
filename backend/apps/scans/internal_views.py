from __future__ import annotations

import hmac
import json
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .auto_export import queue_automatic_defectdojo_export
from .events import append_scan_event
from .groups import dispatch_due_schedules
from .models import QueueState, ScanBatch, ScanEvent, ScanRun
from .normalize import finalize_run_lifecycle, persist_batch_observations
from .tasks import execute_batch

MAX_RESULT_BYTES = 2 * 1024 * 1024
TERMINAL_BATCH_STATUSES = {
    ScanBatch.Status.COMPLETED,
    ScanBatch.Status.FAILED,
    ScanBatch.Status.CANCELLED,
}
FINISHED_BATCH_STATUSES = TERMINAL_BATCH_STATUSES | {ScanBatch.Status.PAUSED}
EWMA_ALPHA = 0.3


def _update_eta(run: ScanRun) -> None:
    """EWMA throughput → remaining ETA in seconds."""
    if run.started_at is None or run.total_batches <= 0:
        return
    elapsed = max(1.0, (timezone.now() - run.started_at).total_seconds())
    done = run.completed_batches + run.failed_batches
    if done <= 0:
        return
    instant_rate = done / (elapsed / 60.0)  # batches per minute
    summary = dict(run.result_summary or {})
    prev = float(summary.get("ewma_batches_per_min") or instant_rate)
    ewma = EWMA_ALPHA * instant_rate + (1.0 - EWMA_ALPHA) * prev
    summary["ewma_batches_per_min"] = round(ewma, 4)
    remaining = max(
        0,
        run.total_batches
        - run.batches.filter(status__in=FINISHED_BATCH_STATUSES).count(),
    )
    if ewma > 0 and remaining > 0:
        run.eta_seconds = max(1, int((remaining / ewma) * 60))
    elif remaining == 0:
        run.eta_seconds = 0
    run.result_summary = summary


def _pause_run_for_deadline(run: ScanRun) -> bool:
    """Pause unfinished batches when the scan window expires. Returns True if paused."""
    if not run.deadline_at or timezone.now() < run.deadline_at:
        return False
    if run.status not in {
        ScanRun.Status.QUEUED,
        ScanRun.Status.RUNNING,
        ScanRun.Status.CANCEL_REQUESTED,
    }:
        return False
    unfinished = run.batches.filter(
        status__in=(ScanBatch.Status.QUEUED, ScanBatch.Status.RUNNING)
    )
    if not unfinished.exists():
        return False
    now = timezone.now()
    unfinished.update(
        status=ScanBatch.Status.PAUSED,
        error="Paused: scan window deadline reached.",
        finished_at=now,
        updated_at=now,
    )
    append_scan_event(
        run,
        "Scan window deadline reached; unfinished batches paused.",
        level=ScanEvent.Level.WARN,
        source="api",
    )
    return True


def _apply_deadline_pauses() -> int:
    """Pause any active runs past their deadline. Returns number of runs affected."""
    now = timezone.now()
    affected = 0
    candidates = (
        ScanRun.objects.filter(
            deadline_at__isnull=False,
            deadline_at__lte=now,
            status__in=(
                ScanRun.Status.QUEUED,
                ScanRun.Status.RUNNING,
            ),
        )
        .order_by("id")[:100]
    )
    for run in candidates:
        with transaction.atomic():
            locked = ScanRun.objects.select_for_update().get(pk=run.pk)
            if _pause_run_for_deadline(locked):
                _aggregate_run(locked)
                affected += 1
    return affected


class HasWorkerToken(BasePermission):
    message = "Valid worker token required."

    def has_permission(self, request: Request, view: object) -> bool:
        expected = settings.WORKER_TOKEN
        provided = request.headers.get("X-Worker-Token", "")
        if not expected or not provided:
            return False
        return hmac.compare_digest(
            provided.encode("utf-8"),
            expected.encode("utf-8"),
        )


class WorkerAPIView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny, HasWorkerToken)

    def get_batch(self, batch_id: int, delivery_id: object) -> ScanBatch | None:
        batch_reference = get_object_or_404(ScanBatch, pk=batch_id)
        if not isinstance(delivery_id, str) or not hmac.compare_digest(
            str(batch_reference.delivery_id), delivery_id
        ):
            return None
        run = ScanRun.objects.select_for_update().get(pk=batch_reference.run_id)
        batch = ScanBatch.objects.select_for_update().get(pk=batch_reference.pk)
        batch.run = run
        return batch


class BatchReconcileView(WorkerAPIView):
    def post(self, request: Request) -> Response:
        broker_epoch = request.data.get("broker_epoch")
        if not isinstance(broker_epoch, str) or not broker_epoch.strip():
            return Response(
                {"detail": "broker_epoch must be a non-empty string."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        broker_epoch = broker_epoch.strip()[:64]
        now = timezone.now()
        stale_before = now - timedelta(
            seconds=settings.SCAN_RECONCILE_STALE_SECONDS
        )
        deadline_paused = _apply_deadline_pauses()

        with transaction.atomic():
            queue_state, _ = QueueState.objects.select_for_update().get_or_create(
                name="scan"
            )
            epoch_changed = queue_state.broker_epoch != broker_epoch
            candidates = ScanBatch.objects.select_for_update().filter(
                status__in=(
                    ScanBatch.Status.QUEUED,
                    ScanBatch.Status.RUNNING,
                ),
                run__status__in=(
                    ScanRun.Status.QUEUED,
                    ScanRun.Status.RUNNING,
                ),
            )
            if epoch_changed:
                candidates.update(queue_recovery_required=True)
            else:
                candidates = candidates.filter(
                    Q(queue_recovery_required=True)
                    | Q(
                        status=ScanBatch.Status.RUNNING,
                        updated_at__lt=stale_before,
                    )
                )
            batches = list(
                candidates.order_by("updated_at", "id")[
                    : settings.SCAN_RECONCILE_BATCH_LIMIT
                ]
            )

            recovered: list[tuple[int, str]] = []
            for batch in batches:
                batch.delivery_id = uuid.uuid4()
                batch.queue_recovery_required = True
                batch.status = ScanBatch.Status.QUEUED
                batch.progress = 0
                batch.result = {}
                batch.error = ""
                batch.claimed_at = None
                batch.finished_at = None
                batch.save(
                    update_fields=(
                        "delivery_id",
                        "queue_recovery_required",
                        "status",
                        "progress",
                        "result",
                        "error",
                        "claimed_at",
                        "finished_at",
                    )
                )
                recovered.append((batch.pk, str(batch.delivery_id)))

            if epoch_changed:
                queue_state.broker_epoch = broker_epoch
                queue_state.save(update_fields=("broker_epoch", "updated_at"))

        published = 0
        failed = 0
        for batch_id, delivery_id in recovered:
            try:
                execute_batch.apply_async(
                    args=(batch_id, delivery_id),
                    queue="scan",
                )
            except Exception:
                failed += 1
                continue

            published += 1
            ScanBatch.objects.filter(
                pk=batch_id,
                delivery_id=delivery_id,
            ).update(
                queue_recovery_required=False,
                updated_at=timezone.now(),
            )

        return Response(
            {
                "epoch_changed": epoch_changed,
                "recovered": len(recovered),
                "published": published,
                "failed": failed,
                "deadline_paused": deadline_paused,
            }
        )


class ScheduleDispatchView(WorkerAPIView):
    """Called by the scans.dispatch_schedules beat task: queue due group scans."""

    def post(self, request: Request) -> Response:
        return Response(dispatch_due_schedules())


def _aggregate_run(run: ScanRun) -> None:
    stats = run.batches.aggregate(
        progress=Avg("progress"),
        completed=Count("id", filter=Q(status=ScanBatch.Status.COMPLETED)),
        failed=Count("id", filter=Q(status=ScanBatch.Status.FAILED)),
        cancelled=Count("id", filter=Q(status=ScanBatch.Status.CANCELLED)),
        paused=Count("id", filter=Q(status=ScanBatch.Status.PAUSED)),
        finished=Count("id", filter=Q(status__in=FINISHED_BATCH_STATUSES)),
    )
    previous_lifecycle = (run.result_summary or {}).get("lifecycle")
    previous_ewma = (run.result_summary or {}).get("ewma_batches_per_min")
    run.progress = round(stats["progress"] or 0)
    run.completed_batches = stats["completed"]
    run.failed_batches = stats["failed"]
    run.result_summary = {
        "completed": stats["completed"],
        "failed": stats["failed"],
        "cancelled": stats["cancelled"],
        "paused": stats["paused"],
    }
    if previous_lifecycle is not None:
        run.result_summary["lifecycle"] = previous_lifecycle
    if previous_ewma is not None:
        run.result_summary["ewma_batches_per_min"] = previous_ewma

    became_terminal = False
    if stats["finished"] == run.total_batches and run.total_batches > 0:
        if run.finished_at is None or run.status not in {
            ScanRun.Status.COMPLETED,
            ScanRun.Status.PARTIAL,
            ScanRun.Status.FAILED,
            ScanRun.Status.CANCELLED,
        }:
            became_terminal = True
        run.finished_at = timezone.now()
        if stats["paused"]:
            run.status = ScanRun.Status.PARTIAL
            run.resume_available = True
            run.eta_seconds = None
        elif stats["cancelled"] or run.status == ScanRun.Status.CANCEL_REQUESTED:
            run.status = ScanRun.Status.CANCELLED
            run.resume_available = False
        elif stats["failed"]:
            run.status = (
                ScanRun.Status.PARTIAL
                if stats["completed"]
                else ScanRun.Status.FAILED
            )
            run.resume_available = False
        else:
            run.status = ScanRun.Status.COMPLETED
            run.progress = 100
            run.resume_available = False
            run.eta_seconds = 0
    else:
        _update_eta(run)

    run.save(
        update_fields=(
            "status",
            "progress",
            "completed_batches",
            "failed_batches",
            "result_summary",
            "finished_at",
            "eta_seconds",
            "resume_available",
            "updated_at",
        )
    )
    if became_terminal:
        if run.status in {
            ScanRun.Status.COMPLETED,
            ScanRun.Status.PARTIAL,
        }:
            try:
                finalize_run_lifecycle(run)
            except Exception:
                pass
        if run.status != ScanRun.Status.PARTIAL or not run.resume_available:
            queue_automatic_defectdojo_export(run)
        elif stats["completed"]:
            queue_automatic_defectdojo_export(run)


class BatchClaimView(WorkerAPIView):
    def post(self, request: Request, batch_id: int) -> Response:
        with transaction.atomic():
            batch = self.get_batch(batch_id, request.data.get("delivery_id"))
            if batch is None:
                return Response(
                    {"detail": "Delivery ID does not match."},
                    status=status.HTTP_409_CONFLICT,
                )

            if batch.status in FINISHED_BATCH_STATUSES:
                return Response(
                    {
                        "terminal": True,
                        "status": batch.status,
                        "cancel_requested": batch.status == ScanBatch.Status.CANCELLED,
                    }
                )

            if _pause_run_for_deadline(batch.run):
                _aggregate_run(batch.run)
                batch.refresh_from_db()
                return Response(
                    {
                        "terminal": True,
                        "status": batch.status,
                        "cancel_requested": False,
                    }
                )

            if batch.run.status in {
                ScanRun.Status.CANCEL_REQUESTED,
                ScanRun.Status.CANCELLED,
            }:
                batch.status = ScanBatch.Status.CANCELLED
                batch.error = "Cancelled before worker claim."
                batch.finished_at = timezone.now()
                batch.save(
                    update_fields=("status", "error", "finished_at", "updated_at")
                )
                _aggregate_run(batch.run)
                return Response(
                    {
                        "terminal": True,
                        "status": batch.status,
                        "cancel_requested": True,
                    }
                )

            now = timezone.now()
            claimed_now = False
            if batch.status == ScanBatch.Status.QUEUED:
                batch.status = ScanBatch.Status.RUNNING
                batch.claimed_at = now
                batch.save(
                    update_fields=("status", "claimed_at", "updated_at")
                )
                claimed_now = True
            if batch.run.status == ScanRun.Status.QUEUED:
                batch.run.status = ScanRun.Status.RUNNING
                batch.run.started_at = now
                batch.run.save(
                    update_fields=("status", "started_at", "updated_at")
                )

            if claimed_now:
                append_scan_event(
                    batch.run,
                    f"Worker claimed batch for {batch.target_address}.",
                    batch=batch,
                    source="worker",
                )

            return Response(
                {
                    "terminal": False,
                    "batch_id": batch.pk,
                    "delivery_id": str(batch.delivery_id),
                    "target": {
                        "address": batch.target_address,
                        "type": batch.target_type,
                    },
                    "modules": batch.run.modules_snapshot,
                }
            )


class BatchProgressView(WorkerAPIView):
    def post(self, request: Request, batch_id: int) -> Response:
        progress = request.data.get("progress")
        if isinstance(progress, bool) or not isinstance(progress, int):
            return Response(
                {"detail": "progress must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if progress < 0 or progress > 100:
            return Response(
                {"detail": "progress must be between 0 and 100."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        message = request.data.get("message", "")
        if message is None:
            message = ""
        if not isinstance(message, str):
            return Response(
                {"detail": "message must be a string."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        message = message.strip()[:2000]

        with transaction.atomic():
            batch = self.get_batch(batch_id, request.data.get("delivery_id"))
            if batch is None:
                return Response(
                    {"detail": "Delivery ID does not match."},
                    status=status.HTTP_409_CONFLICT,
                )
            if batch.status == ScanBatch.Status.RUNNING:
                batch.progress = max(batch.progress, progress)
                batch.save(update_fields=("progress", "updated_at"))
                _aggregate_run(batch.run)
                if message:
                    append_scan_event(
                        batch.run,
                        message,
                        batch=batch,
                        source="worker",
                    )
            return Response(
                {
                    "status": batch.status,
                    "progress": batch.progress,
                    "cancel_requested": batch.run.status
                    == ScanRun.Status.CANCEL_REQUESTED,
                }
            )


class BatchCancelCheckView(WorkerAPIView):
    def get(self, request: Request, batch_id: int) -> Response:
        with transaction.atomic():
            batch = self.get_batch(
                batch_id,
                request.query_params.get("delivery_id"),
            )
            if batch is None:
                return Response(
                    {"detail": "Delivery ID does not match."},
                    status=status.HTTP_409_CONFLICT,
                )
            return Response(
                {
                    "cancel_requested": batch.run.status
                    in {ScanRun.Status.CANCEL_REQUESTED, ScanRun.Status.CANCELLED}
                    or batch.status == ScanBatch.Status.CANCELLED,
                    "status": batch.status,
                }
            )


class BatchCompleteView(WorkerAPIView):
    def post(self, request: Request, batch_id: int) -> Response:
        result = request.data.get("result")
        if not isinstance(result, dict):
            return Response(
                {"detail": "result must be an object."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(json.dumps(result, separators=(",", ":")).encode("utf-8")) > MAX_RESULT_BYTES:
            return Response(
                {"detail": "result exceeds the 2 MiB limit."},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        with transaction.atomic():
            batch = self.get_batch(batch_id, request.data.get("delivery_id"))
            if batch is None:
                return Response(
                    {"detail": "Delivery ID does not match."},
                    status=status.HTTP_409_CONFLICT,
                )
            if batch.status == ScanBatch.Status.COMPLETED:
                return Response({"status": batch.status})
            if batch.status in {ScanBatch.Status.FAILED, ScanBatch.Status.CANCELLED}:
                return Response(
                    {"detail": f"Batch is already {batch.status}."},
                    status=status.HTTP_409_CONFLICT,
                )

            batch.status = ScanBatch.Status.COMPLETED
            batch.progress = 100
            batch.result = result
            batch.error = ""
            batch.finished_at = timezone.now()
            batch.save(
                update_fields=(
                    "status",
                    "progress",
                    "result",
                    "error",
                    "finished_at",
                    "updated_at",
                )
            )
            try:
                obs_count = persist_batch_observations(batch)
            except Exception:
                obs_count = 0
            hosts = result.get("hosts") if isinstance(result.get("hosts"), list) else []
            http_records = (
                result.get("http") if isinstance(result.get("http"), list) else []
            )
            signatures = (
                result.get("signatures")
                if isinstance(result.get("signatures"), list)
                else []
            )
            append_scan_event(
                batch.run,
                (
                    f"Batch completed for {batch.target_address}: "
                    f"{len(hosts)} host(s), {len(http_records)} HTTP observation(s), "
                    f"{len(signatures)} signature(s), {obs_count} observation row(s)."
                ),
                batch=batch,
                source="worker",
            )
            _aggregate_run(batch.run)
            if batch.run.status in {
                ScanRun.Status.COMPLETED,
                ScanRun.Status.PARTIAL,
                ScanRun.Status.FAILED,
                ScanRun.Status.CANCELLED,
            }:
                append_scan_event(
                    batch.run,
                    f"Scan finished with status {batch.run.status} ({batch.run.progress}%).",
                    source="api",
                )
            return Response({"status": batch.status})


class BatchFailView(WorkerAPIView):
    def post(self, request: Request, batch_id: int) -> Response:
        error = request.data.get("error")
        cancelled = request.data.get("cancelled", False)
        if not isinstance(error, str) or not error.strip():
            return Response(
                {"detail": "error must be a non-empty string."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(cancelled, bool):
            return Response(
                {"detail": "cancelled must be boolean."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            batch = self.get_batch(batch_id, request.data.get("delivery_id"))
            if batch is None:
                return Response(
                    {"detail": "Delivery ID does not match."},
                    status=status.HTTP_409_CONFLICT,
                )
            desired_status = (
                ScanBatch.Status.CANCELLED if cancelled else ScanBatch.Status.FAILED
            )
            if batch.status == desired_status:
                return Response({"status": batch.status})
            if batch.status in TERMINAL_BATCH_STATUSES:
                return Response(
                    {"detail": f"Batch is already {batch.status}."},
                    status=status.HTTP_409_CONFLICT,
                )

            batch.status = desired_status
            batch.error = error.strip()[:2000]
            batch.finished_at = timezone.now()
            batch.save(
                update_fields=("status", "error", "finished_at", "updated_at")
            )
            append_scan_event(
                batch.run,
                f"Batch {desired_status} for {batch.target_address}: {batch.error}",
                level=(
                    ScanEvent.Level.WARN
                    if desired_status == ScanBatch.Status.CANCELLED
                    else ScanEvent.Level.ERROR
                ),
                batch=batch,
                source="worker",
            )
            _aggregate_run(batch.run)
            if batch.run.status in {
                ScanRun.Status.COMPLETED,
                ScanRun.Status.PARTIAL,
                ScanRun.Status.FAILED,
                ScanRun.Status.CANCELLED,
            }:
                append_scan_event(
                    batch.run,
                    f"Scan finished with status {batch.run.status} ({batch.run.progress}%).",
                    level=(
                        ScanEvent.Level.ERROR
                        if batch.run.status == ScanRun.Status.FAILED
                        else ScanEvent.Level.WARN
                        if batch.run.status
                        in {ScanRun.Status.PARTIAL, ScanRun.Status.CANCELLED}
                        else ScanEvent.Level.INFO
                    ),
                    source="api",
                )
            return Response({"status": batch.status})
