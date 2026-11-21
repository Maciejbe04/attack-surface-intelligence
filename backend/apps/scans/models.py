from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Target(models.Model):
    class Type(models.TextChoices):
        IP = "ip", "IP address"
        CIDR = "cidr", "CIDR range"
        DOMAIN = "domain", "Domain"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="scan_targets",
    )
    address = models.CharField(max_length=255)
    target_type = models.CharField(max_length=16, choices=Type.choices)
    comment = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("address", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "address"),
                name="scans_target_owner_address_uniq",
            )
        ]

    def __str__(self) -> str:
        return self.address


class ScanRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        CANCEL_REQUESTED = "cancel_requested", "Cancel requested"
        COMPLETED = "completed", "Completed"
        PARTIAL = "partial", "Partial"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="scan_runs",
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    modules_snapshot = models.JSONField(default=list)
    client_request_id = models.CharField(max_length=128, blank=True, default="")
    total_batches = models.PositiveIntegerField(default=0)
    completed_batches = models.PositiveIntegerField(default=0)
    failed_batches = models.PositiveIntegerField(default=0)
    progress = models.PositiveSmallIntegerField(default=0)
    result_summary = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "client_request_id"),
                condition=~Q(client_request_id=""),
                name="scans_run_owner_request_uniq",
            )
        ]

    def __str__(self) -> str:
        return f"scan:{self.pk}:{self.status}"


class ScanBatch(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    run = models.ForeignKey(ScanRun, on_delete=models.CASCADE, related_name="batches")
    target = models.ForeignKey(
        Target,
        on_delete=models.SET_NULL,
        related_name="scan_batches",
        null=True,
        blank=True,
    )
    target_address = models.CharField(max_length=255)
    target_type = models.CharField(max_length=16, choices=Target.Type.choices)
    delivery_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    queue_recovery_required = models.BooleanField(default=False, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    progress = models.PositiveSmallIntegerField(default=0)
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, default="")
    claimed_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=("run", "target", "target_address"),
                condition=Q(target__isnull=False),
                name="scans_batch_run_target_address_uniq",
            )
        ]

    def __str__(self) -> str:
        return f"batch:{self.pk}:{self.status}"


class QueueState(models.Model):
    name = models.CharField(max_length=32, primary_key=True)
    broker_epoch = models.CharField(max_length=64, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"queue:{self.name}"


class ScanEvent(models.Model):
    class Level(models.TextChoices):
        INFO = "info", "Info"
        WARN = "warn", "Warning"
        ERROR = "error", "Error"

    run = models.ForeignKey(ScanRun, on_delete=models.CASCADE, related_name="events")
    batch = models.ForeignKey(
        ScanBatch,
        on_delete=models.SET_NULL,
        related_name="events",
        null=True,
        blank=True,
    )
    level = models.CharField(
        max_length=16,
        choices=Level.choices,
        default=Level.INFO,
        db_index=True,
    )
    source = models.CharField(max_length=32, default="api")
    message = models.CharField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("id",)

    def __str__(self) -> str:
        return f"event:{self.pk}:{self.level}"
