"""Target groups and their recurring scan schedules."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone as dt_timezone

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from .models import GroupSchedule, ScanRun, Target, TargetGroup
from .modules import validate_modules
from .services import TooManyBatches, queue_scan_for_targets

logger = logging.getLogger(__name__)

MAX_GROUP_NAME_LENGTH = 100
MAX_GROUP_SCAN_TARGETS = 10_000
DISPATCH_BATCH_LIMIT = 20
ACTIVE_RUN_STATUSES = (
    ScanRun.Status.QUEUED,
    ScanRun.Status.RUNNING,
    ScanRun.Status.CANCEL_REQUESTED,
)


def normalize_group_name(value: object) -> str:
    """Collapse whitespace; raise ValueError for an empty or too long name."""
    if not isinstance(value, str):
        raise ValueError("Group name must be text.")
    name = " ".join(value.split())
    if not name:
        raise ValueError("Group name is required.")
    if len(name) > MAX_GROUP_NAME_LENGTH:
        raise ValueError(f"Group name must not exceed {MAX_GROUP_NAME_LENGTH} characters.")
    return name


def get_or_create_group(owner: User, name: str) -> tuple[TargetGroup, bool]:
    """Case-insensitive lookup by name, so "DMZ" and "dmz" are the same group."""
    name = normalize_group_name(name)
    existing = TargetGroup.objects.filter(owner=owner, name__iexact=name).first()
    if existing is not None:
        return existing, False
    return TargetGroup.objects.get_or_create(owner=owner, name=name)


def add_targets_to_group(group: TargetGroup, targets: list[Target]) -> int:
    """Add targets (already owned by the group owner). Returns how many were new."""
    if not targets:
        return 0
    through = TargetGroup.targets.through
    present = set(
        through.objects.filter(
            targetgroup_id=group.pk,
            target_id__in=[target.pk for target in targets],
        ).values_list("target_id", flat=True)
    )
    group.targets.add(*targets)
    return len({target.pk for target in targets} - present)


def compute_next_run(schedule: GroupSchedule, after: datetime) -> datetime:
    """First occurrence strictly after ``after`` (UTC, minute precision)."""
    after = after.astimezone(dt_timezone.utc).replace(second=0, microsecond=0)
    if schedule.frequency == GroupSchedule.Frequency.HOURLY:
        return after + timedelta(hours=max(1, schedule.interval_hours))

    candidate = datetime.combine(
        after.date(),
        schedule.time_of_day.replace(second=0, microsecond=0),
        tzinfo=dt_timezone.utc,
    )
    if schedule.frequency == GroupSchedule.Frequency.DAILY:
        if candidate <= after:
            candidate += timedelta(days=1)
        return candidate

    candidate += timedelta(days=(schedule.weekday - candidate.weekday()) % 7)
    if candidate <= after:
        candidate += timedelta(days=7)
    return candidate


def _dispatch_one(schedule: GroupSchedule, now: datetime) -> str:
    group = schedule.group
    occurrence = schedule.next_run_at or now
    previous = schedule.last_run
    if previous is not None and previous.status in ACTIVE_RUN_STATUSES:
        return f"Skipped: previous scan #{previous.pk} is still active."

    targets = list(group.targets.filter(owner_id=group.owner_id).order_by("id"))
    if not targets:
        return "Skipped: the group has no targets."
    if len(targets) > MAX_GROUP_SCAN_TARGETS:
        return f"Skipped: the group has more than {MAX_GROUP_SCAN_TARGETS} targets."

    try:
        modules = validate_modules(schedule.modules_snapshot)
    except Exception:  # noqa: BLE001 - serializer errors carry nested details
        return "Skipped: the saved module configuration is no longer valid."

    try:
        run, _created = queue_scan_for_targets(
            owner=group.owner,
            targets=targets,
            modules=modules,
            # One run per occurrence even if dispatch is retried.
            client_request_id=f"schedule:{schedule.pk}:{occurrence:%Y%m%dT%H%M}",
            group=group,
            schedule=schedule,
        )
    except TooManyBatches as exc:
        return f"Skipped: {exc}"
    schedule.last_run = run
    schedule.last_run_at = now
    return f"Queued scan #{run.pk} for {len(targets)} target(s)."


def dispatch_due_schedules(now: datetime | None = None) -> dict[str, int]:
    """Queue scans for every enabled schedule whose time has come.

    Missed occurrences (stack down) run once and are not replayed; the next run is
    always computed from ``now``.
    """
    now = now or timezone.now()
    dispatched = skipped = 0
    with transaction.atomic():
        due = list(
            GroupSchedule.objects.select_for_update(skip_locked=True, of=("self",))
            .select_related("group", "last_run")
            .filter(enabled=True, next_run_at__lte=now)
            .order_by("next_run_at", "id")[:DISPATCH_BATCH_LIMIT]
        )
        for schedule in due:
            try:
                with transaction.atomic():
                    outcome = _dispatch_one(schedule, now)
            except Exception:
                logger.exception("Schedule %s dispatch failed", schedule.pk)
                outcome = "Failed: could not queue the scan."
            if outcome.startswith("Queued"):
                dispatched += 1
            else:
                skipped += 1
            schedule.last_status = outcome[:500]
            schedule.next_run_at = compute_next_run(schedule, now)
            schedule.save(
                update_fields=(
                    "last_run",
                    "last_run_at",
                    "last_status",
                    "next_run_at",
                    "updated_at",
                )
            )
    return {"due": len(due), "dispatched": dispatched, "skipped": skipped}
