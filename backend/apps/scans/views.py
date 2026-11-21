from __future__ import annotations

from functools import partial

from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .defectdojo import (
    DefectDojoError,
    DefectDojoNotConfigured,
    export_scan_to_defectdojo,
)
from .events import append_scan_event
from .models import ScanBatch, ScanEvent, ScanRun, Target
from .permissions import CanExportFindings, IsAdminOrOperator
from .serializers import (
    ScanCreateSerializer,
    ScanRunListSerializer,
    ScanRunSerializer,
    TargetSerializer,
    is_admin,
)
from .tasks import execute_batch


def _targets_for(user):
    queryset = Target.objects.all()
    return queryset if is_admin(user) else queryset.filter(owner=user)


def _runs_for(user):
    queryset = ScanRun.objects.all()
    return queryset if is_admin(user) else queryset.filter(owner=user)


def _publish_batch(batch_id: int, delivery_id: str) -> None:
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


class TargetListCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsAdminOrOperator()]
        return super().get_permissions()

    def get(self, request: Request) -> Response:
        targets = _targets_for(request.user).order_by("address", "id")
        return Response(TargetSerializer(targets, many=True).data)

    def post(self, request: Request) -> Response:
        serializer = TargetSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        target = serializer.save()
        return Response(
            TargetSerializer(target).data,
            status=status.HTTP_201_CREATED,
        )


class TargetDetailView(APIView):
    permission_classes = (IsAuthenticated, IsAdminOrOperator)

    def delete(self, request: Request, target_id: int) -> Response:
        target = get_object_or_404(_targets_for(request.user), pk=target_id)
        target.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ScanListCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsAdminOrOperator()]
        return super().get_permissions()

    def get(self, request: Request) -> Response:
        runs = (
            _runs_for(request.user)
            .prefetch_related("batches")
            .order_by("-created_at", "-id")
        )
        return Response(ScanRunListSerializer(runs, many=True).data)

    def post(self, request: Request) -> Response:
        serializer = ScanCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        client_request_id = serializer.validated_data.get("client_request_id", "")

        with transaction.atomic():
            if client_request_id:
                existing = (
                    ScanRun.objects.select_for_update()
                    .filter(
                        owner=request.user,
                        client_request_id=client_request_id,
                    )
                    .first()
                )
                if existing is not None:
                    return Response(ScanRunSerializer(existing).data)

            try:
                with transaction.atomic():
                    run = ScanRun.objects.create(
                        owner=request.user,
                        modules_snapshot=serializer.validated_data["modules"],
                        client_request_id=client_request_id,
                        total_batches=len(serializer.context["targets"]),
                    )
            except IntegrityError:
                run = ScanRun.objects.get(
                    owner=request.user,
                    client_request_id=client_request_id,
                )
                return Response(ScanRunSerializer(run).data)

            batches = ScanBatch.objects.bulk_create(
                [
                    ScanBatch(
                        run=run,
                        target=target,
                        target_address=target.address,
                        target_type=target.target_type,
                    )
                    for target in serializer.context["targets"]
                ]
            )
            for batch in batches:
                transaction.on_commit(
                    partial(_publish_batch, batch.pk, str(batch.delivery_id))
                )

            module_ids = [
                module.get("id", "?")
                for module in serializer.validated_data["modules"]
                if isinstance(module, dict)
            ]
            append_scan_event(
                run,
                (
                    f"Queued scan #{run.pk} for {len(batches)} target(s); "
                    f"modules: {', '.join(str(item) for item in module_ids) or 'none'}."
                ),
                source="api",
            )
            for batch in batches:
                append_scan_event(
                    run,
                    f"Batch queued for {batch.target_address} ({batch.target_type}).",
                    batch=batch,
                    source="api",
                )

        run = (
            ScanRun.objects.prefetch_related("batches", "events__batch")
            .get(pk=run.pk)
        )
        return Response(ScanRunSerializer(run).data, status=status.HTTP_201_CREATED)


class ScanDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request: Request, run_id: int) -> Response:
        run = get_object_or_404(
            _runs_for(request.user).prefetch_related("batches", "events__batch"),
            pk=run_id,
        )
        return Response(ScanRunSerializer(run).data)


class ScanCancelView(APIView):
    permission_classes = (IsAuthenticated, IsAdminOrOperator)

    def post(self, request: Request, run_id: int) -> Response:
        with transaction.atomic():
            run = get_object_or_404(
                _runs_for(request.user).select_for_update(),
                pk=run_id,
            )
            if run.status in {
                ScanRun.Status.COMPLETED,
                ScanRun.Status.PARTIAL,
                ScanRun.Status.FAILED,
                ScanRun.Status.CANCELLED,
            }:
                return Response(
                    {"detail": f"Scan is already {run.status}."},
                    status=status.HTTP_409_CONFLICT,
                )

            now = timezone.now()
            run.batches.filter(status=ScanBatch.Status.QUEUED).update(
                status=ScanBatch.Status.CANCELLED,
                error="Cancelled before execution.",
                finished_at=now,
                progress=0,
            )
            stats = run.batches.aggregate(
                progress=Avg("progress"),
                completed=Count(
                    "id", filter=Q(status=ScanBatch.Status.COMPLETED)
                ),
                failed=Count("id", filter=Q(status=ScanBatch.Status.FAILED)),
                cancelled=Count(
                    "id", filter=Q(status=ScanBatch.Status.CANCELLED)
                ),
            )
            has_running = run.batches.filter(status=ScanBatch.Status.RUNNING).exists()
            run.status = (
                ScanRun.Status.CANCEL_REQUESTED
                if has_running
                else ScanRun.Status.CANCELLED
            )
            run.progress = round(stats["progress"] or 0)
            run.completed_batches = stats["completed"]
            run.failed_batches = stats["failed"]
            run.result_summary = {
                "completed": stats["completed"],
                "failed": stats["failed"],
                "cancelled": stats["cancelled"],
            }
            if not has_running:
                run.finished_at = now
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
            if has_running:
                append_scan_event(
                    run,
                    "Cancellation requested; waiting for running batches to stop.",
                    level=ScanEvent.Level.WARN,
                    source="api",
                )
            else:
                append_scan_event(
                    run,
                    "Scan cancelled before worker execution.",
                    level=ScanEvent.Level.WARN,
                    source="api",
                )

        run = (
            ScanRun.objects.prefetch_related("batches", "events__batch")
            .get(pk=run.pk)
        )
        return Response(ScanRunSerializer(run).data)


class ScanDefectDojoExportView(APIView):
    permission_classes = (IsAuthenticated, CanExportFindings)

    def post(self, request: Request, run_id: int) -> Response:
        run = get_object_or_404(
            _runs_for(request.user).prefetch_related("batches"),
            pk=run_id,
        )
        if run.status in {
            ScanRun.Status.QUEUED,
            ScanRun.Status.RUNNING,
            ScanRun.Status.CANCEL_REQUESTED,
        }:
            return Response(
                {"detail": "Only a finished scan can be exported."},
                status=status.HTTP_409_CONFLICT,
            )
        if not run.batches.filter(status=ScanBatch.Status.COMPLETED).exists():
            return Response(
                {"detail": "The scan has no completed batches to export."},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            result = export_scan_to_defectdojo(run)
        except DefectDojoNotConfigured as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except DefectDojoError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(result)
