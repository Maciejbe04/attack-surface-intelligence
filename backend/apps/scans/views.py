from __future__ import annotations

import json

from django.db import transaction
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import ValidationError as SerializerValidationError
from rest_framework.views import APIView

from .auto_export import queue_automatic_defectdojo_export
from .defectdojo import (
    DefectDojoError,
    DefectDojoNotConfigured,
    export_scan_to_defectdojo,
)
from .events import append_scan_event
from .import_targets import MAX_IMPORT_TARGETS, parse_import_payload
from .groups import add_targets_to_group, get_or_create_group, normalize_group_name
from .models import ScanBatch, ScanEvent, ScanRun, Target, TargetGroup
from .modules import validate_modules
from .permissions import CanExportFindings, IsAdminOrOperator
from .serializers import (
    ScanCreateSerializer,
    ScanRunListSerializer,
    ScanRunSerializer,
    TargetSerializer,
    is_admin,
)
from .services import queue_scan_for_targets


def _targets_for(user):
    queryset = Target.objects.all()
    return queryset if is_admin(user) else queryset.filter(owner=user)


def _runs_for(user):
    queryset = ScanRun.objects.all()
    return queryset if is_admin(user) else queryset.filter(owner=user)


class TargetListCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsAdminOrOperator()]
        return super().get_permissions()

    def get(self, request: Request) -> Response:
        """List targets. Optional filters: ?search=, ?group=<id>, ?limit=1..100."""
        targets = _targets_for(request.user).prefetch_related("groups")
        search = request.query_params.get("search", "").strip()[:255]
        if search:
            targets = targets.filter(
                Q(address__icontains=search) | Q(comment__icontains=search)
            )
        group_id = request.query_params.get("group", "").strip()
        if group_id:
            if not group_id.isdigit():
                return Response(
                    {"detail": "group must be a numeric ID."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            targets = targets.filter(groups__id=int(group_id))
        targets = targets.order_by("address", "id")
        limit = request.query_params.get("limit", "").strip()
        if limit:
            if not limit.isdigit() or not 1 <= int(limit) <= 100:
                return Response(
                    {"detail": "limit must be between 1 and 100."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if search:
                # Exact and prefix matches first: what a typeahead user expects.
                ranked = sorted(
                    targets[:500],
                    key=lambda target: (
                        target.address.lower() != search.lower(),
                        not target.address.lower().startswith(search.lower()),
                        target.address,
                    ),
                )
                return Response(TargetSerializer(ranked[: int(limit)], many=True).data)
            targets = targets[: int(limit)]
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


class TargetImportView(APIView):
    permission_classes = (IsAuthenticated, IsAdminOrOperator)

    def post(self, request: Request) -> Response:
        upload = request.FILES.get("file")
        if upload is None:
            return Response(
                {"detail": "Multipart field 'file' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw = upload.read(MAX_IMPORT_TARGETS * 256 + 1)
        parsed = parse_import_payload(filename=upload.name or "hosts.txt", raw=raw)
        if not parsed.targets and parsed.errors:
            return Response(
                {"detail": parsed.errors[0], "errors": parsed.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not parsed.targets:
            return Response(
                {"detail": "No valid targets found in the file."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_scan_raw = request.data.get("start_scan", "true")
        if isinstance(start_scan_raw, bool):
            start_scan = start_scan_raw
        else:
            start_scan = str(start_scan_raw).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }

        modules_raw = request.data.get("modules")
        if modules_raw in (None, ""):
            modules = validate_modules([{"id": "full-pipeline", "filters": {}}])
        else:
            if isinstance(modules_raw, (bytes, bytearray)):
                modules_raw = modules_raw.decode("utf-8")
            if isinstance(modules_raw, str):
                try:
                    modules_raw = json.loads(modules_raw)
                except json.JSONDecodeError:
                    return Response(
                        {"detail": "modules must be valid JSON."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            try:
                modules = validate_modules(modules_raw)
            except SerializerValidationError as exc:
                return Response(
                    {"detail": exc.detail},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        client_request_id = str(
            request.data.get("client_request_id") or ""
        ).strip()[:128]

        owner = request.user
        import_group = None
        group_id_raw = str(request.data.get("group_id") or "").strip()
        group_name_raw = str(request.data.get("group_name") or "").strip()
        if group_id_raw:
            if not group_id_raw.isdigit():
                return Response(
                    {"detail": "group_id must be a numeric ID."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            import_group = TargetGroup.objects.filter(
                pk=int(group_id_raw),
                owner=owner,
            ).first()
            if import_group is None:
                return Response(
                    {"detail": "Group not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        elif group_name_raw:
            try:
                normalize_group_name(group_name_raw)
            except ValueError as exc:
                return Response(
                    {"detail": str(exc)},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        row_group_names = {
            name for item in parsed.targets for name in item.groups
        }
        try:
            for name in row_group_names:
                normalize_group_name(name)
        except ValueError as exc:
            return Response(
                {"detail": f"Invalid group in file: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        addresses = [item.address for item in parsed.targets]
        existing_by_address = {
            target.address: target
            for target in Target.objects.filter(owner=owner, address__in=addresses)
        }
        existing_addresses = set(existing_by_address)

        to_create = [
            Target(
                owner=owner,
                address=item.address,
                target_type=item.target_type,
                comment=item.comment,
            )
            for item in parsed.targets
            if item.address not in existing_addresses
        ]
        if to_create:
            Target.objects.bulk_create(to_create, ignore_conflicts=True)

        all_targets = list(
            Target.objects.filter(owner=owner, address__in=addresses).order_by("id")
        )

        # Group assignment: one group for the whole file plus optional per-row groups.
        groups_touched: dict[int, dict] = {}

        def assign(group: TargetGroup, members: list[Target], created: bool) -> None:
            added = add_targets_to_group(group, members)
            entry = groups_touched.setdefault(
                group.pk,
                {"id": group.pk, "name": group.name, "created": created, "added_count": 0},
            )
            entry["added_count"] += added

        with transaction.atomic():
            if import_group is None and group_name_raw:
                import_group, group_created = get_or_create_group(owner, group_name_raw)
            else:
                group_created = False
            if import_group is not None:
                assign(import_group, all_targets, group_created)
            if row_group_names:
                by_address = {target.address: target for target in all_targets}
                members_by_name: dict[str, list[Target]] = {}
                for item in parsed.targets:
                    target = by_address.get(item.address)
                    if target is None:
                        continue
                    for name in item.groups:
                        members_by_name.setdefault(name, []).append(target)
                for name, members in members_by_name.items():
                    group, created = get_or_create_group(owner, name)
                    assign(group, members, created)
        created_count = sum(
            1 for target in all_targets if target.address not in existing_addresses
        )
        existing_count = len(all_targets) - created_count

        scan_payload = None
        if start_scan and all_targets:
            run, _created = queue_scan_for_targets(
                owner=owner,
                targets=all_targets,
                modules=modules,
                client_request_id=client_request_id,
                group=import_group,
            )
            run = (
                ScanRun.objects.prefetch_related("batches", "events__batch")
                .get(pk=run.pk)
            )
            scan_payload = ScanRunSerializer(run).data

        return Response(
            {
                "created_count": created_count,
                "existing_count": existing_count,
                "total_count": len(all_targets),
                "parse_errors": parsed.errors,
                "skipped_duplicates_in_file": parsed.skipped_duplicates_in_file,
                "target_ids": [target.pk for target in all_targets],
                "targets": TargetSerializer(
                    Target.objects.filter(
                        pk__in=[target.pk for target in all_targets[:500]]
                    )
                    .prefetch_related("groups")
                    .order_by("id"),
                    many=True,
                ).data,
                "groups": sorted(groups_touched.values(), key=lambda item: item["name"]),
                "scan": scan_payload,
            },
            status=status.HTTP_201_CREATED,
        )


class ScanListCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsAdminOrOperator()]
        return super().get_permissions()

    def get(self, request: Request) -> Response:
        runs = (
            _runs_for(request.user)
            .select_related("group")
            .prefetch_related("batches")
            .order_by("-created_at", "-id")
        )
        return Response(ScanRunListSerializer(runs, many=True).data)

    def post(self, request: Request) -> Response:
        serializer = ScanCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        client_request_id = serializer.validated_data.get("client_request_id", "")
        run, created = queue_scan_for_targets(
            owner=request.user,
            targets=serializer.context["targets"],
            modules=serializer.validated_data["modules"],
            client_request_id=client_request_id,
        )
        run = (
            ScanRun.objects.prefetch_related("batches", "events__batch")
            .get(pk=run.pk)
        )
        return Response(
            ScanRunSerializer(run).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


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
                queue_automatic_defectdojo_export(run)

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
        run.defectdojo_export_status = ScanRun.DefectDojoExportStatus.SENT
        run.defectdojo_export_detail = (
            f"Sent {result.get('finding_count', 0)} finding(s)"
            + (
                f" to test #{result.get('test')}."
                if result.get("test")
                else "."
            )
        )[:500]
        run.save(
            update_fields=(
                "defectdojo_export_status",
                "defectdojo_export_detail",
                "updated_at",
            )
        )
        append_scan_event(
            run,
            f"Manual DefectDojo export finished: {run.defectdojo_export_detail}",
            source="defectdojo",
        )
        return Response(result)
