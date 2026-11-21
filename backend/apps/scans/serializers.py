from __future__ import annotations

from django.contrib.auth.models import User
from django.db import IntegrityError
from rest_framework import serializers

from .models import ScanBatch, ScanRun, Target
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

    class Meta:
        model = Target
        fields = ("id", "address", "type", "comment", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

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


class ScanRunSerializer(serializers.ModelSerializer):
    modules = serializers.JSONField(source="modules_snapshot", read_only=True)
    batches = ScanBatchSerializer(many=True, read_only=True)
    targets = serializers.SerializerMethodField()

    def get_targets(self, instance: ScanRun) -> list[str]:
        return [batch.target_address for batch in instance.batches.all()]

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
            "created_at",
            "started_at",
            "finished_at",
            "batches",
        )


class ScanRunListSerializer(ScanRunSerializer):
    class Meta(ScanRunSerializer.Meta):
        fields = tuple(field for field in ScanRunSerializer.Meta.fields if field != "batches")


class ScanCreateSerializer(serializers.Serializer):
    target_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=1000,
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
