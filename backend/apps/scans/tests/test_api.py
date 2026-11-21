from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import UserProfile
from apps.scans.models import ScanBatch, ScanRun, Target


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

    def test_target_rbac_and_owner_scope(self) -> None:
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
        self.assertEqual([item["id"] for item in response.json()], [own_target.id])
        self.assertNotContains(response, other_target.address)

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

        with patch("apps.scans.views.execute_batch.apply_async") as publish:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(reverse("scan-list"), payload, format="json")

        self.assertEqual(response.status_code, 201)
        run = ScanRun.objects.get()
        batch = run.batches.get()
        self.assertEqual(batch.target_address, target.address)
        self.assertEqual(run.modules_snapshot[0]["filters"]["profile"], "discovery-fast")
        self.assertEqual(response.json()["targets"], [target.address])
        publish.assert_called_once_with(
            args=(batch.id, str(batch.delivery_id)),
            queue="scan",
        )

        with patch("apps.scans.views.execute_batch.apply_async") as publish:
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
            "apps.scans.views.execute_batch.apply_async",
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

    def test_scan_rejects_unsafe_modules_and_inaccessible_targets(self) -> None:
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
        self.assertEqual(response.status_code, 400)

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

    def test_scan_reads_are_owner_scoped_and_viewer_cannot_cancel(self) -> None:
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
        self.assertEqual([item["id"] for item in response.json()], [own_run.id])
        response = self.client.get(reverse("scan-detail", args=(other_run.id,)))
        self.assertEqual(response.status_code, 404)
        response = self.client.post(reverse("scan-cancel", args=(own_run.id,)))
        self.assertEqual(response.status_code, 403)


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
            {**self.identity, "progress": 45},
            format="json",
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)

        complete_url = reverse("internal-batch-complete", args=(self.batch.id,))
        payload = {**self.identity, "result": {"hosts": []}}
        response = self.client.post(
            complete_url,
            payload,
            format="json",
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
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
