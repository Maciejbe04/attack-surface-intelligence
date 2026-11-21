"""Recompute result_summary.curiosity for completed/partial runs."""

from django.core.management.base import BaseCommand

from apps.scans.curiosity import compute_curiosity_summary
from apps.scans.models import ScanRun


class Command(BaseCommand):
    help = "Backfill analytical curiosity summaries on existing scan runs."

    def handle(self, *args, **options):
        updated = 0
        for run in ScanRun.objects.filter(
            status__in=(ScanRun.Status.COMPLETED, ScanRun.Status.PARTIAL)
        ).iterator():
            summary = dict(run.result_summary or {})
            summary["curiosity"] = compute_curiosity_summary(run)
            run.result_summary = summary
            run.save(update_fields=("result_summary", "updated_at"))
            updated += 1
        self.stdout.write(self.style.SUCCESS(f"Updated {updated} run(s)."))
