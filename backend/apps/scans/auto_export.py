from __future__ import annotations

import logging
import threading

from django.db import close_old_connections, transaction

from .defectdojo import DefectDojoError, DefectDojoNotConfigured, export_scan_to_defectdojo
from .events import append_scan_event
from .models import ScanEvent, ScanRun

logger = logging.getLogger(__name__)

TERMINAL_RUN_STATUSES = {
    ScanRun.Status.COMPLETED,
    ScanRun.Status.PARTIAL,
    ScanRun.Status.FAILED,
    ScanRun.Status.CANCELLED,
}


def queue_automatic_defectdojo_export(run: ScanRun) -> bool:
    if run.status not in TERMINAL_RUN_STATUSES:
        return False
    if run.completed_batches < 1:
        return False
    if run.defectdojo_export_status != ScanRun.DefectDojoExportStatus.NONE:
        return False

    run.defectdojo_export_status = ScanRun.DefectDojoExportStatus.PENDING
    run.defectdojo_export_detail = "Waiting to send findings to DefectDojo."
    run.save(
        update_fields=(
            "defectdojo_export_status",
            "defectdojo_export_detail",
            "updated_at",
        )
    )
    append_scan_event(
        run,
        "Queuing automatic DefectDojo export…",
        source="defectdojo",
    )
    run_id = run.pk
    transaction.on_commit(lambda: _start_export_thread(run_id))
    return True


def _start_export_thread(run_id: int) -> None:
    def runner() -> None:
        close_old_connections()
        try:
            perform_automatic_defectdojo_export(run_id)
        finally:
            close_old_connections()

    thread = threading.Thread(
        target=runner,
        name=f"defectdojo-export-{run_id}",
        daemon=True,
    )
    thread.start()


def perform_automatic_defectdojo_export(run_id: int) -> None:
    try:
        with transaction.atomic():
            run = ScanRun.objects.select_for_update().get(pk=run_id)
            if run.defectdojo_export_status not in {
                ScanRun.DefectDojoExportStatus.PENDING,
                ScanRun.DefectDojoExportStatus.NONE,
            }:
                return
            run.defectdojo_export_status = ScanRun.DefectDojoExportStatus.SENDING
            run.defectdojo_export_detail = "Sending findings to DefectDojo…"
            run.save(
                update_fields=(
                    "defectdojo_export_status",
                    "defectdojo_export_detail",
                    "updated_at",
                )
            )
        append_scan_event(
            run,
            "Sending findings to DefectDojo…",
            source="defectdojo",
        )

        try:
            result = export_scan_to_defectdojo(
                ScanRun.objects.prefetch_related("batches").get(pk=run_id)
            )
        except DefectDojoNotConfigured as exc:
            _finish_export(
                run_id,
                status=ScanRun.DefectDojoExportStatus.SKIPPED,
                detail=str(exc),
                level=ScanEvent.Level.INFO,
                message=f"DefectDojo export skipped: {exc}",
            )
            return
        except DefectDojoError as exc:
            _finish_export(
                run_id,
                status=ScanRun.DefectDojoExportStatus.FAILED,
                detail=str(exc)[:500],
                level=ScanEvent.Level.ERROR,
                message=f"DefectDojo export failed: {exc}",
            )
            return

        finding_count = int(result.get("finding_count") or 0)
        test_id = result.get("test")
        detail = (
            f"Sent {finding_count} finding(s)"
            + (f" to test #{test_id}." if test_id else ".")
        )
        _finish_export(
            run_id,
            status=ScanRun.DefectDojoExportStatus.SENT,
            detail=detail[:500],
            level=ScanEvent.Level.INFO,
            message=f"DefectDojo export finished: {detail}",
        )
    except Exception:
        logger.exception("Automatic DefectDojo export crashed for scan %s", run_id)
        try:
            _finish_export(
                run_id,
                status=ScanRun.DefectDojoExportStatus.FAILED,
                detail="Unexpected DefectDojo export error.",
                level=ScanEvent.Level.ERROR,
                message="DefectDojo export failed unexpectedly.",
            )
        except Exception:
            logger.exception(
                "Could not persist DefectDojo export failure for scan %s", run_id
            )


def _finish_export(
    run_id: int,
    *,
    status: str,
    detail: str,
    level: str,
    message: str,
) -> None:
    with transaction.atomic():
        run = ScanRun.objects.select_for_update().get(pk=run_id)
        run.defectdojo_export_status = status
        run.defectdojo_export_detail = detail[:500]
        run.save(
            update_fields=(
                "defectdojo_export_status",
                "defectdojo_export_detail",
                "updated_at",
            )
        )
    append_scan_event(run, message[:2000], level=level, source="defectdojo")
