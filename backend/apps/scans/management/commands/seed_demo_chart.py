"""Seed synthetic completed scans so the Changes-over-time chart has demo data."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.scans.models import ScanBatch, ScanEvent, ScanRun, Target, TargetGroup

DEMO_PREFIX = "demo-chart-"
LAB_GROUP = "lab-local"
LAB_ADDRESS = "lab-target.surfacex.local"

# Staggered lifecycle counts across the last week (index 0 = oldest).
DEMO_LIFECYCLES: list[dict[str, int]] = [
    {"NEW": 14, "CHANGED": 0, "MISSING": 0, "FLAKY": 0, "GONE": 0, "UNCHANGED": 0},
    {"NEW": 3, "CHANGED": 2, "MISSING": 0, "FLAKY": 0, "GONE": 0, "UNCHANGED": 11},
    {"NEW": 1, "CHANGED": 4, "MISSING": 1, "FLAKY": 0, "GONE": 0, "UNCHANGED": 12},
    {"NEW": 5, "CHANGED": 2, "MISSING": 0, "FLAKY": 1, "GONE": 0, "UNCHANGED": 14},
    {"NEW": 0, "CHANGED": 3, "MISSING": 2, "FLAKY": 1, "GONE": 1, "UNCHANGED": 15},
    {"NEW": 2, "CHANGED": 1, "MISSING": 1, "FLAKY": 0, "GONE": 2, "UNCHANGED": 16},
    {"NEW": 4, "CHANGED": 2, "MISSING": 1, "FLAKY": 0, "GONE": 0, "UNCHANGED": 18},
    {"NEW": 1, "CHANGED": 3, "MISSING": 0, "FLAKY": 1, "GONE": 1, "UNCHANGED": 19},
]


class Command(BaseCommand):
    help = (
        "Create a week of completed demo scans with lifecycle summaries "
        "so the Dashboard Changes-over-time chart is populated locally."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default="admin",
            help="Owner username (default: admin).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Recreate demo-chart runs even if they already exist.",
        )

    def handle(self, *args, **options):
        username = options["username"]
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(
                self.style.WARNING(
                    f"User '{username}' missing — skip (run bootstrap_admin first)."
                )
            )
            return

        existing = ScanRun.objects.filter(
            owner=user,
            client_request_id__startswith=DEMO_PREFIX,
        )
        if existing.exists() and not options["force"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Demo chart already seeded for {username} "
                    f"({existing.count()} runs). Use --force to recreate."
                )
            )
            return

        with transaction.atomic():
            if options["force"]:
                existing.delete()
            created = self._seed_user(user)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created} demo chart scans for {username}."
            )
        )

    def _seed_user(self, user: User) -> int:
        group = TargetGroup.objects.filter(owner=user, name=LAB_GROUP).first()
        target = Target.objects.filter(owner=user, address=LAB_ADDRESS).first()
        if target is None:
            target = Target.objects.filter(owner=user).order_by("id").first()

        now = timezone.now()
        created = 0
        for index, lifecycle in enumerate(DEMO_LIFECYCLES):
            # Spread across ~7 days ending a few minutes ago.
            offset_hours = (len(DEMO_LIFECYCLES) - 1 - index) * 22 + 3
            finished = now - timedelta(hours=offset_hours)
            started = finished - timedelta(minutes=8 + index)
            request_id = f"{DEMO_PREFIX}{index + 1:02d}"
            curiosity_level = ("high", "medium", "low", "info")[index % 4]
            run = ScanRun(
                owner=user,
                status=ScanRun.Status.COMPLETED,
                modules_snapshot=[
                    {"id": "host-discovery", "filters": {"profile": "discovery-fast"}},
                    {"id": "http-fingerprint", "filters": {}},
                ],
                client_request_id=request_id,
                total_batches=1,
                completed_batches=1,
                failed_batches=0,
                progress=100,
                result_summary={
                    "lifecycle": lifecycle,
                    "curiosity": {
                        "level": curiosity_level,
                        "hosts_with_open_ports": 1,
                        "open_ports": max(1, sum(lifecycle.values()) // 4),
                    },
                    "demo": True,
                },
                group=group,
                window_seconds=3600,
                started_at=started,
                finished_at=finished,
            )
            run.save()
            # auto_now_add locks created_at; backdate for realistic ordering.
            ScanRun.objects.filter(pk=run.pk).update(
                created_at=started - timedelta(seconds=20),
                updated_at=finished,
            )

            if target is not None:
                batch = ScanBatch.objects.create(
                    run=run,
                    target=target,
                    target_address=target.address,
                    target_type=target.target_type,
                    status=ScanBatch.Status.COMPLETED,
                    progress=100,
                    result={
                        "hosts": [
                            {
                                "address": target.address,
                                "status": "up",
                                "ports": [
                                    {
                                        "port": 80,
                                        "protocol": "tcp",
                                        "state": "open",
                                        "attrs": {"curiosity": curiosity_level},
                                    }
                                ],
                            }
                        ]
                    },
                    finished_at=finished,
                )
                ScanBatch.objects.filter(pk=batch.pk).update(
                    created_at=started,
                    updated_at=finished,
                )

            ScanEvent.objects.create(
                run=run,
                level=ScanEvent.Level.INFO,
                source="demo",
                message=(
                    f"Demo chart seed #{index + 1}: "
                    + ", ".join(f"{key}={value}" for key, value in lifecycle.items() if value)
                ),
            )
            created += 1

        return created
