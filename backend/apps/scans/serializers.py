from __future__ import annotations

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.utils import timezone
from rest_framework import serializers

from .groups import compute_next_run, normalize_group_name
from .models import GroupSchedule, ScanBatch, ScanEvent, ScanRun, Target, TargetGroup
from .modules import validate_modules
from .validation import normalize_target


def is_admin(user: User) -> bool:
    if user.is_superuser:
        return True
    try:
        return user.profile.role == "admin"
    except User.profile.RelatedObjectDoesNotExist:
        return False


class TargetSerializer(serializers.ModelSerializer):
    type = serializers.ChoiceField(source="target_type", choices=Target.Type.choices)
    groups = serializers.SerializerMethodField()

    def get_groups(self, instance: Target) -> list[dict]:
        # Callers prefetch "groups"; a fresh instance has no memberships yet.
        if instance.pk is None:
            return []
        return [{"id": group.pk, "name": group.name} for group in instance.groups.all()]

    class Meta:
        model = Target
        fields = ("id", "address", "type", "comment", "groups", "created_at", "updated_at")
        read_only_fields = ("id", "groups", "created_at", "updated_at")

    def validate(self, attrs: dict) -> dict:
        target_type = attrs.get(
            "target_type", getattr(self.instance, "target_type", None)
        )
        address = attrs.get("address", getattr(self.instance, "address", ""))
        try:
            attrs["address"] = normalize_target(address, target_type)
        except ValueError as exc:
            raise serializers.ValidationError({"address": str(exc)}) from exc
        return attrs

    def create(self, validated_data: dict) -> Target:
        validated_data["owner"] = self.context["request"].user
        try:
            return super().create(validated_data)
        except IntegrityError as exc:
            raise serializers.ValidationError(
                {"address": "This target is already saved."}
            ) from exc


class ScanBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScanBatch
        fields = (
            "id",
            "target_address",
            "target_type",
            "status",
            "progress",
            "result",
            "error",
            "created_at",
            "claimed_at",
            "finished_at",
        )


class ScanEventSerializer(serializers.ModelSerializer):
    target_address = serializers.SerializerMethodField()

    def get_target_address(self, instance: ScanEvent) -> str | None:
        batch = instance.batch
        return batch.target_address if batch is not None else None

    class Meta:
        model = ScanEvent
        fields = (
            "id",
            "batch_id",
            "target_address",
            "level",
            "source",
            "message",
            "created_at",
        )


class ScanRunSerializer(serializers.ModelSerializer):
    modules = serializers.JSONField(source="modules_snapshot", read_only=True)
    batches = ScanBatchSerializer(many=True, read_only=True)
    events = ScanEventSerializer(many=True, read_only=True)
    targets = serializers.SerializerMethodField()
    group_name = serializers.SerializerMethodField()
    scheduled = serializers.SerializerMethodField()

    def get_targets(self, instance: ScanRun) -> list[str]:
        return [batch.target_address for batch in instance.batches.all()]

    def get_group_name(self, instance: ScanRun) -> str | None:
        return instance.group.name if instance.group_id and instance.group else None

    def get_scheduled(self, instance: ScanRun) -> bool:
        return instance.schedule_id is not None

    class Meta:
        model = ScanRun
        fields = (
            "id",
            "status",
            "modules",
            "targets",
            "client_request_id",
            "total_batches",
            "completed_batches",
            "failed_batches",
            "progress",
            "result_summary",
            "error",
            "defectdojo_export_status",
            "defectdojo_export_detail",
            "group_id",
            "group_name",
            "scheduled",
            "created_at",
            "started_at",
            "finished_at",
            "batches",
            "events",
        )


class ScanRunListSerializer(ScanRunSerializer):
    class Meta(ScanRunSerializer.Meta):
        fields = tuple(
            field
            for field in ScanRunSerializer.Meta.fields
            if field not in {"batches", "events"}
        )


class ScanCreateSerializer(serializers.Serializer):
    target_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=10000,
    )
    modules = serializers.JSONField()
    client_request_id = serializers.CharField(
        max_length=128,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )

    def validate_target_ids(self, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Target IDs must be unique.")
        user = self.context["request"].user
        queryset = Target.objects.filter(pk__in=value)
        if not is_admin(user):
            queryset = queryset.filter(owner=user)
        targets = list(queryset.order_by("id"))
        if len(targets) != len(value):
            raise serializers.ValidationError(
                "Every target must be a saved target accessible to this user."
            )
        target_by_id = {target.pk: target for target in targets}
        self.context["targets"] = [target_by_id[target_id] for target_id in value]
        return value

    def validate_modules(self, value: object) -> list[dict]:
        return validate_modules(value)


class GroupScheduleSerializer(serializers.ModelSerializer):
    modules = serializers.JSONField(source="modules_snapshot")
    time_of_day = serializers.TimeField(format="%H:%M", input_formats=["%H:%M", "%H:%M:%S"])
    interval_hours = serializers.IntegerField(min_value=1, max_value=168, default=24)
    weekday = serializers.IntegerField(min_value=0, max_value=6, default=0)
    last_run_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = GroupSchedule
        fields = (
            "enabled",
            "frequency",
            "interval_hours",
            "time_of_day",
            "weekday",
            "modules",
            "next_run_at",
            "last_run_at",
            "last_run_id",
            "last_status",
        )
        read_only_fields = ("next_run_at", "last_run_at", "last_run_id", "last_status")

    def validate_modules(self, value: object) -> list[dict]:
        return validate_modules(value)

    def save(self, **kwargs) -> GroupSchedule:
        schedule = super().save(**kwargs)
        # Any change re-plans from now; a disabled schedule has no next run.
        schedule.next_run_at = (
            compute_next_run(schedule, timezone.now()) if schedule.enabled else None
        )
        schedule.save(update_fields=("next_run_at", "updated_at"))
        return schedule


class TargetGroupSerializer(serializers.ModelSerializer):
    target_count = serializers.IntegerField(read_only=True)
    schedule = serializers.SerializerMethodField()
    owner = serializers.CharField(source="owner.username", read_only=True)

    def get_schedule(self, instance: TargetGroup) -> dict | None:
        try:
            schedule = instance.schedule
        except GroupSchedule.DoesNotExist:
            return None
        return GroupScheduleSerializer(schedule).data

    def validate_name(self, value: str) -> str:
        try:
            name = normalize_group_name(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        owner = self.instance.owner if self.instance else self.context["request"].user
        clash = TargetGroup.objects.filter(owner=owner, name__iexact=name)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("A group with this name already exists.")
        return name

    class Meta:
        model = TargetGroup
        fields = (
            "id",
            "name",
            "description",
            "owner",
            "target_count",
            "schedule",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "owner", "target_count", "schedule", "created_at", "updated_at")


class GroupMembershipSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=("add", "remove"))
    target_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=10000,
    )

    def validate_target_ids(self, value: list[int]) -> list[int]:
        group: TargetGroup = self.context["group"]
        ids = sorted(set(value))
        # Members must belong to the group owner, also when an admin edits the group.
        targets = list(Target.objects.filter(pk__in=ids, owner_id=group.owner_id))
        if len(targets) != len(ids):
            raise serializers.ValidationError(
                "Every target must be a saved target of the group owner."
            )
        self.context["targets"] = targets
        return ids


class GroupScanSerializer(serializers.Serializer):
    modules = serializers.JSONField()
    client_request_id = serializers.CharField(
        max_length=128,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )

    def validate_modules(self, value: object) -> list[dict]:
        return validate_modules(value)
