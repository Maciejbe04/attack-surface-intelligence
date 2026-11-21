from __future__ import annotations

import hmac
import json

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

from .models import ScanBatch, ScanRun

MAX_RESULT_BYTES = 2 * 1024 * 1024
TERMINAL_BATCH_STATUSES = {
    ScanBatch.Status.COMPLETED,
    ScanBatch.Status.FAILED,
    ScanBatch.Status.CANCELLED,
}


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


def _aggregate_run(run: ScanRun) -> None:
    stats = run.batches.aggregate(
        progress=Avg("progress"),
        completed=Count("id", filter=Q(status=ScanBatch.Status.COMPLETED)),
        failed=Count("id", filter=Q(status=ScanBatch.Status.FAILED)),
        cancelled=Count("id", filter=Q(status=ScanBatch.Status.CANCELLED)),
        terminal=Count("id", filter=Q(status__in=TERMINAL_BATCH_STATUSES)),
    )
    run.progress = round(stats["progress"] or 0)
    run.completed_batches = stats["completed"]
    run.failed_batches = stats["failed"]
    run.result_summary = {
        "completed": stats["completed"],
        "failed": stats["failed"],
        "cancelled": stats["cancelled"],
    }

    if stats["terminal"] == run.total_batches:
        run.finished_at = timezone.now()
        if stats["cancelled"] or run.status == ScanRun.Status.CANCEL_REQUESTED:
            run.status = ScanRun.Status.CANCELLED
        elif stats["failed"]:
            run.status = (
                ScanRun.Status.PARTIAL
                if stats["completed"]
                else ScanRun.Status.FAILED
            )
        else:
            run.status = ScanRun.Status.COMPLETED
            run.progress = 100

    run.save(
        update_fields=(
            "status",
            "progress",
            "completed_batches",
            "failed_batches",
            "result_summary",
            "finished_at",
            "updated_at",
        )
    )


class BatchClaimView(WorkerAPIView):
    def post(self, request: Request, batch_id: int) -> Response:
        with transaction.atomic():
            batch = self.get_batch(batch_id, request.data.get("delivery_id"))
            if batch is None:
                return Response(
                    {"detail": "Delivery ID does not match."},
                    status=status.HTTP_409_CONFLICT,
                )

            if batch.status in TERMINAL_BATCH_STATUSES:
                return Response(
                    {
                        "terminal": True,
                        "status": batch.status,
                        "cancel_requested": batch.status == ScanBatch.Status.CANCELLED,
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
            if batch.status == ScanBatch.Status.QUEUED:
                batch.status = ScanBatch.Status.RUNNING
                batch.claimed_at = now
                batch.save(
                    update_fields=("status", "claimed_at", "updated_at")
                )
            if batch.run.status == ScanRun.Status.QUEUED:
                batch.run.status = ScanRun.Status.RUNNING
                batch.run.started_at = now
                batch.run.save(
                    update_fields=("status", "started_at", "updated_at")
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
            _aggregate_run(batch.run)
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
            _aggregate_run(batch.run)
            return Response({"status": batch.status})
