from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import UserProfile
from apps.scans.auto_export import perform_automatic_defectdojo_export
from apps.scans.defectdojo import build_generic_findings_report
from apps.scans.models import QueueState, ScanBatch, ScanRun, Target


def create_user(username: str, role: str) -> User:
    user = User.objects.create_user(username=username, password="test-password")
    UserProfile.objects.create(user=user, role=role)
    return user


class PublicScanAPITests(TestCase):
    def setUp(self) -> None:
        self.operator = create_user("operator", UserProfile.Role.OPERATOR)
        self.viewer = create_user("viewer", UserProfile.Role.VIEWER)
        self.other_operator = create_user("other", UserProfile.Role.OPERATOR)
        self.client = APIClient()

    def test_target_rbac_shared_workspace(self) -> None:
        other_target = Target.objects.create(
            owner=self.other_operator,
            address="other.example.test",
            target_type=Target.Type.DOMAIN,
        )
        own_target = Target.objects.create(
            owner=self.viewer,
            address="viewer.example.test",
            target_type=Target.Type.DOMAIN,
        )
        self.client.force_login(self.viewer)

        response = self.client.get(reverse("target-list"))
        self.assertEqual(response.status_code, 200)
        # Shared team workspace: a read-only user sees every target.
        self.assertEqual(
            sorted(item["id"] for item in response.json()),
            sorted([own_target.id, other_target.id]),
        )

        response = self.client.post(
            reverse("target-list"),
            {"address": "192.0.2.1", "type": "ip", "comment": ""},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.operator)
        response = self.client.post(
            reverse("target-list"),
            {
                "address": "Täst.Example.test.",
                "type": "domain",
                "comment": "mail",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["address"], "xn--tst-qla.example.test")

    def test_scan_creation_snapshots_and_publishes_after_commit(self) -> None:
        target = Target.objects.create(
            owner=self.operator,
            address="192.0.2.10",
            target_type=Target.Type.IP,
        )
        self.client.force_login(self.operator)
        payload = {
            "target_ids": [target.id],
            "modules": [{"id": "port-scan", "filters": {}}],
            "client_request_id": "request-1",
        }

        with patch("apps.scans.services.execute_batch.apply_async") as publish:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(reverse("scan-list"), payload, format="json")

        self.assertEqual(response.status_code, 201)
        run = ScanRun.objects.get()
        batch = run.batches.get()
        self.assertEqual(batch.target_address, target.address)
        self.assertEqual(run.modules_snapshot[0]["filters"]["profile"], "discovery-fast")
        self.assertEqual(response.json()["targets"], [target.address])
        self.assertGreaterEqual(len(response.json()["events"]), 2)
        self.assertIn("Queued scan", response.json()["events"][0]["message"])
        publish.assert_called_once_with(
            args=(batch.id, str(batch.delivery_id)),
            queue="scan",
        )

        with patch("apps.scans.services.execute_batch.apply_async") as publish:
            response = self.client.post(reverse("scan-list"), payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ScanRun.objects.count(), 1)
        publish.assert_not_called()

    def test_broker_publish_failure_is_persisted_in_postgres(self) -> None:
        target = Target.objects.create(
            owner=self.operator,
            address="192.0.2.11",
            target_type=Target.Type.IP,
        )
        self.client.force_login(self.operator)

        with patch(
            "apps.scans.services.execute_batch.apply_async",
            side_effect=ConnectionError("broker unavailable"),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    reverse("scan-list"),
                    {
                        "target_ids": [target.id],
                        "modules": [{"id": "host-discovery", "filters": {}}],
                        "client_request_id": "publish-failure",
                    },
                    format="json",
                )

        self.assertEqual(response.status_code, 201)
        run = ScanRun.objects.get(client_request_id="publish-failure")
        self.assertEqual(run.status, ScanRun.Status.FAILED)
        self.assertEqual(run.failed_batches, 1)
        self.assertIn("Queue publish failed", run.batches.get().error)

    def test_scan_rejects_unsafe_modules_but_allows_team_targets(self) -> None:
        target = Target.objects.create(
            owner=self.other_operator,
            address="192.0.2.20",
            target_type=Target.Type.IP,
        )
        self.client.force_login(self.operator)

        response = self.client.post(
            reverse("scan-list"),
            {
                "target_ids": [target.id],
                "modules": [{"id": "unknown", "filters": {}}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            reverse("scan-list"),
            {
                "target_ids": [target.id],
                "modules": [
                    {"id": "full-pipeline", "filters": {}},
                    {"id": "port-scan", "filters": {}},
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            reverse("scan-list"),
            {
                "target_ids": [target.id],
                "modules": [{"id": "port-scan", "filters": {}}],
            },
            format="json",
        )
        # A target saved by a teammate can be scanned by any operator.
        self.assertEqual(response.status_code, 201)

    def test_cancel_marks_unclaimed_batches_cancelled(self) -> None:
        run = ScanRun.objects.create(
            owner=self.operator,
            modules_snapshot=[{"id": "host-discovery", "filters": {}}],
            total_batches=1,
        )
        ScanBatch.objects.create(
            run=run,
            target_address="192.0.2.30",
            target_type=Target.Type.IP,
        )
        self.client.force_login(self.operator)

        response = self.client.post(reverse("scan-cancel", args=(run.id,)))
        self.assertEqual(response.status_code, 200)
        run.refresh_from_db()
        self.assertEqual(run.status, ScanRun.Status.CANCELLED)
        self.assertEqual(run.batches.get().status, ScanBatch.Status.CANCELLED)

    def test_scans_are_shared_and_viewer_cannot_cancel(self) -> None:
        own_run = ScanRun.objects.create(
            owner=self.viewer,
            modules_snapshot=[],
        )
        other_run = ScanRun.objects.create(
            owner=self.other_operator,
            modules_snapshot=[],
        )
        self.client.force_login(self.viewer)

        response = self.client.get(reverse("scan-list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            sorted(item["id"] for item in response.json()),
            sorted([own_run.id, other_run.id]),
        )
        response = self.client.get(reverse("scan-detail", args=(other_run.id,)))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse("scan-cancel", args=(own_run.id,)))
        self.assertEqual(response.status_code, 403)

    def test_finished_scan_can_be_exported_to_defectdojo(self) -> None:
        analyst = create_user("analyst", UserProfile.Role.ANALYST)
        run = ScanRun.objects.create(
            owner=analyst,
            status=ScanRun.Status.COMPLETED,
            modules_snapshot=[],
            total_batches=1,
            completed_batches=1,
            progress=100,
            finished_at=timezone.now(),
        )
        ScanBatch.objects.create(
            run=run,
            target_address="192.0.2.80",
            target_type=Target.Type.IP,
            status=ScanBatch.Status.COMPLETED,
            progress=100,
            result={"hosts": [{"address": "192.0.2.80", "ports": []}]},
            finished_at=timezone.now(),
        )
        self.client.force_login(analyst)

        with patch(
            "apps.scans.views.export_scan_to_defectdojo",
            return_value={
                "finding_count": 1,
                "test": 42,
                "message": "Imported",
            },
        ) as export:
            response = self.client.post(
                reverse("scan-defectdojo-export", args=(run.id,))
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["finding_count"], 1)
        export.assert_called_once()

        self.client.force_login(self.viewer)
        response = self.client.post(
            reverse("scan-defectdojo-export", args=(run.id,))
        )
        self.assertEqual(response.status_code, 403)

    def test_defectdojo_report_contains_stable_attack_surface_findings(self) -> None:
        run = ScanRun.objects.create(
            owner=self.operator,
            status=ScanRun.Status.COMPLETED,
            modules_snapshot=[],
            total_batches=1,
            completed_batches=1,
            progress=100,
            finished_at=timezone.now(),
        )
        ScanBatch.objects.create(
            run=run,
            target_address="app.example.test",
            target_type=Target.Type.DOMAIN,
            status=ScanBatch.Status.COMPLETED,
            progress=100,
            result={
                "hosts": [
                    {
                        "address": "192.0.2.81",
                        "ports": [
                            {
                                "port": 443,
                                "protocol": "tcp",
                                "service": "https",
                                "product": "nginx",
                                "version": "1.27",
                            }
                        ],
                    }
                ],
                "http": [
                    {
                        "url": "https://app.example.test:443",
                        "tech": ["nginx"],
                    }
                ],
                "signatures": [
                    {
                        "endpoint": "https://app.example.test:443",
                        "technology": "nginx",
                        "confidence": 80,
                        "evidence": "server header",
                    }
                ],
            },
            finished_at=timezone.now(),
        )

        report = build_generic_findings_report(
            ScanRun.objects.prefetch_related("batches").get(pk=run.pk)
        )

        self.assertEqual(report["type"], "SurfaceX")
        self.assertEqual(len(report["findings"]), 3)
        self.assertEqual(
            {finding["vuln_id_from_tool"] for finding in report["findings"]},
            {
                "surfacex.live-host",
                "surfacex.open-service",
                "surfacex.technology",
            },
        )
        by_rule = {
            finding["vuln_id_from_tool"]: finding for finding in report["findings"]
        }
        # Port 443 curiosity → Info; high-confidence tech → Medium
        self.assertEqual(by_rule["surfacex.open-service"]["severity"], "Info")
        self.assertIn("Curiosity: info", by_rule["surfacex.open-service"]["description"])
        self.assertEqual(by_rule["surfacex.technology"]["severity"], "Medium")
        self.assertEqual(by_rule["surfacex.live-host"]["severity"], "Info")
        self.assertEqual(
            len(
                {
                    finding["unique_id_from_tool"]
                    for finding in report["findings"]
                }
            ),
            3,
        )

    def test_defectdojo_report_ignores_passive_discovery_payload(self) -> None:
        run = ScanRun.objects.create(
            owner=self.operator,
            status=ScanRun.Status.COMPLETED,
            modules_snapshot=[{"id": "passive-discovery", "filters": {}}],
            total_batches=1,
            completed_batches=1,
            progress=100,
            finished_at=timezone.now(),
        )
        ScanBatch.objects.create(
            run=run,
            target_address="example.com",
            target_type=Target.Type.DOMAIN,
            status=ScanBatch.Status.COMPLETED,
            progress=100,
            result={
                "hosts": [],
                "http": [],
                "signatures": [],
                "passive": {
                    "query": "example.com",
                    "type": "domain",
                    "subdomains": ["www.example.com"],
                    "rdap": {"name": "Example Org", "country": "US"},
                    "sources": {"crt_sh": "ok", "rdap": "ok"},
                    "warnings": [],
                },
            },
            finished_at=timezone.now(),
        )

        report = build_generic_findings_report(
            ScanRun.objects.prefetch_related("batches").get(pk=run.pk)
        )
        self.assertEqual(report["findings"], [])


@override_settings(WORKER_TOKEN="worker-test-token")
class InternalWorkerAPITests(TestCase):
    def setUp(self) -> None:
        self.owner = create_user("queue-owner", UserProfile.Role.OPERATOR)
        self.run = ScanRun.objects.create(
            owner=self.owner,
            modules_snapshot=[{"id": "host-discovery", "filters": {}}],
            total_batches=1,
        )
        self.batch = ScanBatch.objects.create(
            run=self.run,
            target_address="192.0.2.40",
            target_type=Target.Type.IP,
        )
        self.client = APIClient()
        self.headers = {"HTTP_X_WORKER_TOKEN": "worker-test-token"}
        self.identity = {"delivery_id": str(self.batch.delivery_id)}

    def test_token_is_required(self) -> None:
        response = self.client.post(
            reverse("internal-batch-claim", args=(self.batch.id,)),
            self.identity,
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_claim_progress_complete_and_idempotency(self) -> None:
        claim_url = reverse("internal-batch-claim", args=(self.batch.id,))
        response = self.client.post(
            claim_url,
            self.identity,
            format="json",
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["terminal"])

        response = self.client.post(
            reverse("internal-batch-progress", args=(self.batch.id,)),
            {
                **self.identity,
                "progress": 45,
                "message": "Starting nmap for test target.",
            },
            format="json",
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            self.run.events.filter(message="Starting nmap for test target.").exists()
        )

        complete_url = reverse("internal-batch-complete", args=(self.batch.id,))
        payload = {
            **self.identity,
            "result": {"hosts": [{"address": "192.0.2.40", "ports": []}]},
        }
        with patch("apps.scans.auto_export._start_export_thread") as start_export:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    complete_url,
                    payload,
                    format="json",
                    **self.headers,
                )
        self.assertEqual(response.status_code, 200)
        self.run.refresh_from_db()
        self.assertEqual(
            self.run.defectdojo_export_status,
            ScanRun.DefectDojoExportStatus.PENDING,
        )
        start_export.assert_called_once_with(self.run.id)

        with patch(
            "apps.scans.auto_export.export_scan_to_defectdojo",
            return_value={
                "finding_count": 1,
                "test": 7,
                "message": "Imported",
            },
        ) as export:
            perform_automatic_defectdojo_export(self.run.id)
        export.assert_called_once()

        response = self.client.post(
            complete_url,
            payload,
            format="json",
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)

        self.batch.refresh_from_db()
        self.run.refresh_from_db()
        self.assertEqual(self.batch.status, ScanBatch.Status.COMPLETED)
        self.assertEqual(self.run.status, ScanRun.Status.COMPLETED)
        self.assertEqual(self.run.progress, 100)
        self.assertEqual(
            self.run.defectdojo_export_status,
            ScanRun.DefectDojoExportStatus.SENT,
        )
        self.client.force_login(self.owner)
        detail = self.client.get(reverse("scan-detail", args=(self.run.id,)))
        self.assertEqual(detail.status_code, 200)
        messages = [event["message"] for event in detail.json()["events"]]
        self.assertTrue(any("Batch completed" in message for message in messages))
        self.assertTrue(
            any("DefectDojo export finished" in message for message in messages)
        )

    def test_bad_delivery_id_is_rejected(self) -> None:
        response = self.client.post(
            reverse("internal-batch-claim", args=(self.batch.id,)),
            {"delivery_id": "not-the-delivery"},
            format="json",
            **self.headers,
        )
        self.assertEqual(response.status_code, 409)

    def test_running_batch_observes_cancellation(self) -> None:
        self.client.post(
            reverse("internal-batch-claim", args=(self.batch.id,)),
            self.identity,
            format="json",
            **self.headers,
        )
        self.client.force_login(self.owner)
        response = self.client.post(reverse("scan-cancel", args=(self.run.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], ScanRun.Status.CANCEL_REQUESTED)

        response = self.client.get(
            reverse("internal-batch-cancel", args=(self.batch.id,)),
            {"delivery_id": str(self.batch.delivery_id)},
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["cancel_requested"])

        response = self.client.post(
            reverse("internal-batch-fail", args=(self.batch.id,)),
            {**self.identity, "error": "cancelled", "cancelled": True},
            format="json",
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, ScanRun.Status.CANCELLED)

    def test_progress_reports_cancel_after_deadline_pause(self) -> None:
        self.client.post(
            reverse("internal-batch-claim", args=(self.batch.id,)),
            self.identity,
            format="json",
            **self.headers,
        )
        self.run.deadline_at = timezone.now() - timedelta(seconds=1)
        self.run.save(update_fields=("deadline_at", "updated_at"))

        response = self.client.post(
            reverse("internal-batch-progress", args=(self.batch.id,)),
            {**self.identity, "progress": 55, "message": "still scanning"},
            format="json",
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["cancel_requested"])
        self.assertEqual(response.json()["status"], ScanBatch.Status.PAUSED)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, ScanBatch.Status.PAUSED)

    @override_settings(
        SCAN_RECONCILE_STALE_SECONDS=600,
        SCAN_RECONCILE_BATCH_LIMIT=100,
    )
    def test_reconcile_republishes_stale_running_and_pending_recovery_batches(
        self,
    ) -> None:
        QueueState.objects.create(name="scan", broker_epoch="current-epoch")
        stale_running = ScanBatch.objects.create(
            run=self.run,
            target_address="192.0.2.41",
            target_type=Target.Type.IP,
            status=ScanBatch.Status.RUNNING,
            progress=60,
            claimed_at=timezone.now() - timedelta(minutes=20),
        )
        fresh = ScanBatch.objects.create(
            run=self.run,
            target_address="192.0.2.42",
            target_type=Target.Type.IP,
        )
        stale_at = timezone.now() - timedelta(minutes=20)
        ScanBatch.objects.filter(pk__in=(self.batch.pk, stale_running.pk)).update(
            updated_at=stale_at
        )
        ScanBatch.objects.filter(pk=self.batch.pk).update(
            queue_recovery_required=True
        )
        old_delivery_ids = {
            self.batch.pk: self.batch.delivery_id,
            stale_running.pk: stale_running.delivery_id,
        }

        with patch("apps.scans.internal_views.execute_batch.apply_async") as publish:
            response = self.client.post(
                reverse("internal-batch-reconcile"),
                {"broker_epoch": "current-epoch"},
                format="json",
                **self.headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "epoch_changed": False,
                "recovered": 2,
                "published": 2,
                "failed": 0,
                "deadline_paused": 0,
            },
        )
        recovered = list(
            ScanBatch.objects.filter(pk__in=old_delivery_ids)
            .order_by("pk")
        )
        for batch in recovered:
            self.assertEqual(batch.status, ScanBatch.Status.QUEUED)
            self.assertEqual(batch.progress, 0)
            self.assertIsNone(batch.claimed_at)
            self.assertNotEqual(batch.delivery_id, old_delivery_ids[batch.pk])
            publish.assert_any_call(
                args=(batch.pk, str(batch.delivery_id)),
                queue="scan",
            )

        fresh.refresh_from_db()
        self.assertEqual(fresh.status, ScanBatch.Status.QUEUED)
        publish_count = publish.call_count
        self.assertEqual(publish_count, 2)

    @override_settings(
        SCAN_RECONCILE_STALE_SECONDS=600,
        SCAN_RECONCILE_BATCH_LIMIT=1,
    )
    def test_broker_epoch_change_recovers_all_active_batches_and_retries_publish(
        self,
    ) -> None:
        QueueState.objects.create(name="scan", broker_epoch="old-epoch")
        remaining = ScanBatch.objects.create(
            run=self.run,
            target_address="192.0.2.43",
            target_type=Target.Type.IP,
        )
        ScanBatch.objects.filter(pk=self.batch.pk).update(
            updated_at=timezone.now() - timedelta(minutes=1)
        )
        old_delivery_id = self.batch.delivery_id
        reconcile_url = reverse("internal-batch-reconcile")

        with patch(
            "apps.scans.internal_views.execute_batch.apply_async",
            side_effect=ConnectionError("broker unavailable"),
        ):
            response = self.client.post(
                reconcile_url,
                {"broker_epoch": "new-epoch"},
                format="json",
                **self.headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "epoch_changed": True,
                "recovered": 1,
                "published": 0,
                "failed": 1,
                "deadline_paused": 0,
            },
        )
        self.batch.refresh_from_db()
        remaining.refresh_from_db()
        failed_delivery_id = self.batch.delivery_id
        self.assertNotEqual(failed_delivery_id, old_delivery_id)
        self.assertTrue(self.batch.queue_recovery_required)
        self.assertTrue(remaining.queue_recovery_required)

        with patch("apps.scans.internal_views.execute_batch.apply_async") as publish:
            response = self.client.post(
                reconcile_url,
                {"broker_epoch": "new-epoch"},
                format="json",
                **self.headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["epoch_changed"], False)
        self.assertEqual(response.json()["published"], 1)
        self.batch.refresh_from_db()
        self.assertNotEqual(self.batch.delivery_id, failed_delivery_id)
        self.assertFalse(self.batch.queue_recovery_required)
        remaining.refresh_from_db()
        self.assertTrue(remaining.queue_recovery_required)
        publish.assert_called_once_with(
            args=(self.batch.pk, str(self.batch.delivery_id)),
            queue="scan",
        )

    def test_mixed_batch_results_finish_run_as_partial(self) -> None:
        second = ScanBatch.objects.create(
            run=self.run,
            target_address="192.0.2.41",
            target_type=Target.Type.IP,
        )
        self.run.total_batches = 2
        self.run.save(update_fields=("total_batches", "updated_at"))

        for batch in (self.batch, second):
            self.client.post(
                reverse("internal-batch-claim", args=(batch.id,)),
                {"delivery_id": str(batch.delivery_id)},
                format="json",
                **self.headers,
            )

        self.client.post(
            reverse("internal-batch-complete", args=(self.batch.id,)),
            {
                "delivery_id": str(self.batch.delivery_id),
                "result": {"hosts": []},
            },
            format="json",
            **self.headers,
        )
        self.client.post(
            reverse("internal-batch-fail", args=(second.id,)),
            {
                "delivery_id": str(second.delivery_id),
                "error": "scanner failed",
                "cancelled": False,
            },
            format="json",
            **self.headers,
        )

        self.run.refresh_from_db()
        self.assertEqual(self.run.status, ScanRun.Status.PARTIAL)
        self.assertEqual(self.run.completed_batches, 1)
        self.assertEqual(self.run.failed_batches, 1)
