from __future__ import annotations

from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .audit import record_audit
from .groups import MAX_GROUP_SCAN_TARGETS, add_targets_to_group
from .models import GroupSchedule, ScanRun, TargetGroup
from .permissions import IsAdminOrOperator
from .serializers import (
    GroupMembershipSerializer,
    GroupScanSerializer,
    GroupScheduleSerializer,
    ScanRunSerializer,
    TargetGroupSerializer,
    is_admin,
)
from .services import queue_scan_for_targets


def groups_for(user):
    queryset = TargetGroup.objects.select_related("owner", "schedule").annotate(
        target_count=Count("targets", distinct=True)
    )
    return queryset if is_admin(user) else queryset.filter(owner=user)


def _get_group(request: Request, group_id: int) -> TargetGroup:
    return get_object_or_404(groups_for(request.user), pk=group_id)


def _group_payload(request: Request, group_id: int) -> dict:
    return TargetGroupSerializer(_get_group(request, group_id)).data


class ReadOrOperatorMixin:
    """Everyone signed in may read; admin/operator may change."""

    def get_permissions(self):
        if self.request.method in {"GET", "HEAD", "OPTIONS"}:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsAdminOrOperator()]


class GroupListCreateView(ReadOrOperatorMixin, APIView):
    def get(self, request: Request) -> Response:
        groups = groups_for(request.user).order_by("name", "id")
        return Response(TargetGroupSerializer(groups, many=True).data)

    def post(self, request: Request) -> Response:
        serializer = TargetGroupSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        group = serializer.save(owner=request.user)
        record_audit(
            actor=request.user,
            action="group.create",
            object_type="group",
            object_id=group.pk,
            summary=f"Created group {group.name}",
        )
        return Response(
            _group_payload(request, group.pk),
            status=status.HTTP_201_CREATED,
        )


class GroupDetailView(ReadOrOperatorMixin, APIView):
    def get(self, request: Request, group_id: int) -> Response:
        return Response(_group_payload(request, group_id))

    def patch(self, request: Request, group_id: int) -> Response:
        group = _get_group(request, group_id)
        serializer = TargetGroupSerializer(
            group,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(_group_payload(request, group_id))

    def delete(self, request: Request, group_id: int) -> Response:
        # Deleting a group never deletes its targets or past scans.
        group = _get_group(request, group_id)
        name = group.name
        group.delete()
        record_audit(
            actor=request.user,
            action="group.delete",
            object_type="group",
            object_id=group_id,
            summary=f"Deleted group {name}",
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class GroupTargetsView(APIView):
    permission_classes = (IsAuthenticated, IsAdminOrOperator)

    def post(self, request: Request, group_id: int) -> Response:
        group = _get_group(request, group_id)
        serializer = GroupMembershipSerializer(data=request.data, context={"group": group})
        serializer.is_valid(raise_exception=True)
        targets = serializer.context["targets"]
        if serializer.validated_data["action"] == "add":
            changed = add_targets_to_group(group, targets)
        else:
            through = TargetGroup.targets.through
            changed, _ = through.objects.filter(
                targetgroup_id=group.pk,
                target_id__in=[target.pk for target in targets],
            ).delete()
        payload = _group_payload(request, group_id)
        payload["changed_count"] = changed
        return Response(payload)


class GroupScanView(APIView):
    permission_classes = (IsAuthenticated, IsAdminOrOperator)

    def post(self, request: Request, group_id: int) -> Response:
        group = _get_group(request, group_id)
        serializer = GroupScanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        targets = list(group.targets.filter(owner_id=group.owner_id).order_by("id"))
        if not targets:
            return Response(
                {"detail": "The group has no targets."},
                status=status.HTTP_409_CONFLICT,
            )
        if len(targets) > MAX_GROUP_SCAN_TARGETS:
            return Response(
                {"detail": f"A group scan is limited to {MAX_GROUP_SCAN_TARGETS} targets."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        run, created = queue_scan_for_targets(
            owner=group.owner,
            targets=targets,
            modules=serializer.validated_data["modules"],
            client_request_id=serializer.validated_data.get("client_request_id", ""),
            group=group,
            window_seconds=serializer.validated_data.get("window_seconds"),
        )
        run = ScanRun.objects.select_related("group").prefetch_related(
            "batches", "events__batch"
        ).get(pk=run.pk)
        if created:
            record_audit(
                actor=request.user,
                action="scan.queue",
                object_type="scan",
                object_id=run.pk,
                summary=f"Queued group scan #{run.pk} for {group.name}",
            )
        return Response(
            ScanRunSerializer(run).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class GroupScheduleView(APIView):
    permission_classes = (IsAuthenticated, IsAdminOrOperator)

    def put(self, request: Request, group_id: int) -> Response:
        group = _get_group(request, group_id)
        try:
            instance = group.schedule
        except GroupSchedule.DoesNotExist:
            instance = None
        serializer = GroupScheduleSerializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(group=group)
        record_audit(
            actor=request.user,
            action="schedule.change",
            object_type="group",
            object_id=group_id,
            summary=f"Updated schedule for group {group.name}",
        )
        return Response(_group_payload(request, group_id))

    def delete(self, request: Request, group_id: int) -> Response:
        group = _get_group(request, group_id)
        GroupSchedule.objects.filter(group=group).delete()
        record_audit(
            actor=request.user,
            action="schedule.change",
            object_type="group",
            object_id=group_id,
            summary=f"Removed schedule for group {group.name}",
        )
        return Response(_group_payload(request, group_id))
