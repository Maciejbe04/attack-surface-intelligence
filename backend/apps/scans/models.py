from __future__ import annotations

import uuid
from datetime import time

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

    class DefectDojoExportStatus(models.TextChoices):
        NONE = "none", "None"
        PENDING = "pending", "Pending"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    defectdojo_export_status = models.CharField(
        max_length=16,
        choices=DefectDojoExportStatus.choices,
        default=DefectDojoExportStatus.NONE,
        db_index=True,
    )
    defectdojo_export_detail = models.CharField(max_length=500, blank=True, default="")
    group = models.ForeignKey(
        "TargetGroup",
        on_delete=models.SET_NULL,
        related_name="runs",
        null=True,
        blank=True,
    )
    schedule = models.ForeignKey(
        "GroupSchedule",
        on_delete=models.SET_NULL,
        related_name="runs",
        null=True,
        blank=True,
    )
    window_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Optional scan window length in seconds; null means no deadline.",
    )
    deadline_at = models.DateTimeField(null=True, blank=True, db_index=True)
    eta_seconds = models.PositiveIntegerField(null=True, blank=True)
    resume_available = models.BooleanField(default=False)
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
        PAUSED = "paused", "Paused"

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
                fields=("run", "target"),
                condition=Q(target__isnull=False),
                name="scans_batch_run_target_uniq",
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


class TargetGroup(models.Model):
    """Named set of targets owned by one user. A target can belong to many groups."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="target_groups",
    )
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=500, blank=True, default="")
    targets = models.ManyToManyField(Target, related_name="groups", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "name"),
                name="scans_group_owner_name_uniq",
            )
        ]

    def __str__(self) -> str:
        return self.name


class GroupSchedule(models.Model):
    """Recurring scan of a whole group. Times are UTC."""

    class Frequency(models.TextChoices):
        HOURLY = "hourly", "Every N hours"
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"

    group = models.OneToOneField(
        TargetGroup,
        on_delete=models.CASCADE,
        related_name="schedule",
    )
    enabled = models.BooleanField(default=True)
    frequency = models.CharField(max_length=16, choices=Frequency.choices)
    interval_hours = models.PositiveSmallIntegerField(default=24)
    time_of_day = models.TimeField(default=time(2, 0))
    weekday = models.PositiveSmallIntegerField(
        default=0,
        help_text="0 = Monday … 6 = Sunday",
    )
    modules_snapshot = models.JSONField(default=list)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_run = models.ForeignKey(
        ScanRun,
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )
    last_status = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"schedule:{self.group_id}:{self.frequency}"


class Observation(models.Model):
    """Normalized finding from a scan batch (host/port/http/tech/cert)."""

    class EntityType(models.TextChoices):
        HOST = "host", "Host"
        PORT = "port", "Port"
        HTTP = "http", "HTTP endpoint"
        TECH = "tech", "Technology"
        CERT = "cert", "TLS certificate"
        SIGNATURE = "signature", "Signature match"

    class Lifecycle(models.TextChoices):
        NEW = "NEW", "New"
        CHANGED = "CHANGED", "Changed"
        MISSING = "MISSING", "Missing"
        FLAKY = "FLAKY", "Flaky"
        GONE = "GONE", "Gone"
        UNCHANGED = "UNCHANGED", "Unchanged"

    class Source(models.TextChoices):
        SCANNER = "scanner", "Scanner"
        IMPORT = "import", "Import"

    run = models.ForeignKey(ScanRun, on_delete=models.CASCADE, related_name="observations")
    target = models.ForeignKey(
        Target,
        on_delete=models.SET_NULL,
        related_name="observations",
        null=True,
        blank=True,
    )
    target_address = models.CharField(max_length=255, db_index=True)
    entity_type = models.CharField(max_length=16, choices=EntityType.choices, db_index=True)
    entity_key = models.CharField(max_length=512, db_index=True)
    lifecycle = models.CharField(
        max_length=16,
        choices=Lifecycle.choices,
        default=Lifecycle.NEW,
        db_index=True,
    )
    attrs = models.JSONField(default=dict, blank=True)
    source = models.CharField(
        max_length=16,
        choices=Source.choices,
        default=Source.SCANNER,
    )
    miss_streak = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("entity_type", "entity_key", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("run", "entity_key"),
                name="scans_observation_run_key_uniq",
            )
        ]
        indexes = [
            models.Index(fields=("run", "lifecycle"), name="scans_obser_run_id_99cba9_idx"),
            models.Index(
                fields=("target_address", "entity_type"),
                name="scans_obser_target__8acc2a_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.entity_type}:{self.entity_key}:{self.lifecycle}"


class FingerprintEvidence(models.Model):
    observation = models.ForeignKey(
        Observation,
        on_delete=models.CASCADE,
        related_name="evidence",
    )
    kind = models.CharField(max_length=32, default="summary")
    summary = models.CharField(max_length=500, blank=True, default="")
    # Encrypted payload (AES-GCM envelope). Empty when encryption is unavailable.
    ciphertext = models.TextField(blank=True, default="")
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("id",)

    def __str__(self) -> str:
        return f"evidence:{self.pk}:{self.kind}"


class AuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    action = models.CharField(max_length=64, db_index=True)
    object_type = models.CharField(max_length=64, blank=True, default="")
    object_id = models.CharField(max_length=64, blank=True, default="")
    summary = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-id",)

    def __str__(self) -> str:
        return f"audit:{self.pk}:{self.action}"
