from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import UserProfile
from apps.scans.crypto import open_sealed, seal
from apps.scans.models import Observation, ScanBatch, ScanRun, Target
from apps.scans.models import TargetGroup
from apps.scans.normalize import (
    finalize_run_lifecycle,
    persist_batch_observations,
    previous_completed_run,
    same_scan_scope,
)
from apps.scans.signatures import evaluate_signature, load_signatures, match_http_records


def create_user(username: str, role: str) -> User:
    user = User.objects.create_user(username=username, password="test-password")
    UserProfile.objects.create(user=user, role=role)
    return user


class NormalizeLifecycleTests(TestCase):
    def setUp(self) -> None:
        self.owner = create_user("ops", UserProfile.Role.OPERATOR)
        self.target = Target.objects.create(
            owner=self.owner,
            address="192.0.2.50",
            target_type=Target.Type.IP,
        )

    def _run_with_batch(self, result: dict) -> ScanRun:
        run = ScanRun.objects.create(
            owner=self.owner,
            status=ScanRun.Status.RUNNING,
            modules_snapshot=[{"id": "full-pipeline", "filters": {}}],
            total_batches=1,
            started_at=timezone.now(),
        )
        batch = ScanBatch.objects.create(
            run=run,
            target=self.target,
            target_address=self.target.address,
            target_type=self.target.target_type,
            status=ScanBatch.Status.COMPLETED,
            progress=100,
            result=result,
            finished_at=timezone.now(),
        )
        persist_batch_observations(batch)
        run.status = ScanRun.Status.COMPLETED
        run.finished_at = timezone.now()
        run.completed_batches = 1
        run.progress = 100
        run.save()
        finalize_run_lifecycle(run)
        return run

    def test_previous_completed_run_matches_same_host_not_other(self) -> None:
        first = self._run_with_batch(
            {
                "hosts": [
                    {
                        "address": "192.0.2.50",
                        "status": "up",
                        "ports": [{"port": 80, "protocol": "tcp", "state": "open"}],
                    }
                ]
            }
        )
        other_target = Target.objects.create(
            owner=self.owner,
            address="198.51.100.10",
            target_type=Target.Type.IP,
        )
        other = ScanRun.objects.create(
            owner=self.owner,
            status=ScanRun.Status.COMPLETED,
            finished_at=timezone.now(),
            total_batches=1,
            completed_batches=1,
            progress=100,
        )
        ScanBatch.objects.create(
            run=other,
            target=other_target,
            target_address=other_target.address,
            target_type=other_target.target_type,
            status=ScanBatch.Status.COMPLETED,
            progress=100,
            result={},
            finished_at=timezone.now(),
        )
        second = ScanRun.objects.create(
            owner=self.owner,
            status=ScanRun.Status.COMPLETED,
            modules_snapshot=[{"id": "full-pipeline", "filters": {}}],
            finished_at=timezone.now(),
            total_batches=1,
            completed_batches=1,
            progress=100,
        )
        ScanBatch.objects.create(
            run=second,
            target=self.target,
            target_address=self.target.address,
            target_type=self.target.target_type,
            status=ScanBatch.Status.COMPLETED,
            progress=100,
            result={},
            finished_at=timezone.now(),
        )
        prev = previous_completed_run(second)
        self.assertEqual(prev, first)
        self.assertTrue(same_scan_scope(second, first))
        self.assertFalse(same_scan_scope(second, other))

    def test_previous_completed_run_matches_same_modules_only(self) -> None:
        pipeline = self._run_with_batch(
            {
                "hosts": [
                    {
                        "address": "192.0.2.50",
                        "status": "up",
                        "ports": [{"port": 80, "protocol": "tcp", "state": "open"}],
                    }
                ]
            }
        )
        tls_older = ScanRun.objects.create(
            owner=self.owner,
            status=ScanRun.Status.COMPLETED,
            modules_snapshot=[{"id": "tls-cert", "filters": {}}],
            finished_at=timezone.now() - timedelta(minutes=5),
            total_batches=1,
            completed_batches=1,
            progress=100,
        )
        ScanBatch.objects.create(
            run=tls_older,
            target=self.target,
            target_address=self.target.address,
            target_type=self.target.target_type,
            status=ScanBatch.Status.COMPLETED,
            progress=100,
            result={},
            finished_at=timezone.now() - timedelta(minutes=5),
        )
        tls_newer = ScanRun.objects.create(
            owner=self.owner,
            status=ScanRun.Status.COMPLETED,
            modules_snapshot=[{"id": "tls-cert", "filters": {}}],
            finished_at=timezone.now(),
            total_batches=1,
            completed_batches=1,
            progress=100,
        )
        ScanBatch.objects.create(
            run=tls_newer,
            target=self.target,
            target_address=self.target.address,
            target_type=self.target.target_type,
            status=ScanBatch.Status.COMPLETED,
            progress=100,
            result={},
            finished_at=timezone.now(),
        )
        prev = previous_completed_run(tls_newer)
        self.assertEqual(prev, tls_older)
        self.assertFalse(same_scan_scope(tls_newer, pipeline))

    def test_previous_completed_run_matches_same_group(self) -> None:
        group = TargetGroup.objects.create(owner=self.owner, name="lab")
        group.targets.add(self.target)
        older = ScanRun.objects.create(
            owner=self.owner,
            group=group,
            status=ScanRun.Status.COMPLETED,
            modules_snapshot=[{"id": "full-pipeline", "filters": {}}],
            finished_at=timezone.now(),
            total_batches=1,
            completed_batches=1,
            progress=100,
        )
        ScanBatch.objects.create(
            run=older,
            target=self.target,
            target_address=self.target.address,
            target_type=self.target.target_type,
            status=ScanBatch.Status.COMPLETED,
            progress=100,
            result={},
            finished_at=timezone.now(),
        )
        host_only = self._run_with_batch(
            {
                "hosts": [
                    {
                        "address": "192.0.2.50",
                        "status": "up",
                        "ports": [{"port": 443, "protocol": "tcp", "state": "open"}],
                    }
                ]
            }
        )
        newer = ScanRun.objects.create(
            owner=self.owner,
            group=group,
            status=ScanRun.Status.COMPLETED,
            modules_snapshot=[{"id": "full-pipeline", "filters": {}}],
            finished_at=timezone.now(),
            total_batches=1,
            completed_batches=1,
            progress=100,
        )
        ScanBatch.objects.create(
            run=newer,
            target=self.target,
            target_address=self.target.address,
            target_type=self.target.target_type,
            status=ScanBatch.Status.COMPLETED,
            progress=100,
            result={},
            finished_at=timezone.now(),
        )
        prev = previous_completed_run(newer)
        self.assertEqual(prev, older)
        self.assertFalse(same_scan_scope(newer, host_only))

    def test_normalize_and_lifecycle_new_then_changed_gone(self) -> None:
        first = self._run_with_batch(
            {
                "hosts": [
                    {
                        "address": "192.0.2.50",
                        "status": "up",
                        "ports": [
                            {"port": 80, "protocol": "tcp", "state": "open", "service": "http"}
                        ],
                    }
                ],
                "http": [
                    {
                        "url": "http://192.0.2.50/",
                        "status_code": 200,
                        "title": "Home",
                        "tech": ["nginx"],
                        "header": {"server": "nginx"},
                    }
                ],
                "signatures": [
                    {
                        "technology": "nginx",
                        "endpoint": "http://192.0.2.50/",
                        "confidence": 40,
                        "level": "medium",
                    }
                ],
            }
        )
        self.assertTrue(first.observations.filter(lifecycle=Observation.Lifecycle.NEW).exists())
        self.assertGreaterEqual(first.observations.count(), 3)

        second = self._run_with_batch(
            {
                "hosts": [
                    {
                        "address": "192.0.2.50",
                        "status": "up",
                        "ports": [
                            {
                                "port": 80,
                                "protocol": "tcp",
                                "state": "open",
                                "service": "http",
                                "product": "nginx",
                            }
                        ],
                    }
                ],
                "http": [
                    {
                        "url": "http://192.0.2.50/",
                        "status_code": 200,
                        "title": "Changed",
                        "tech": ["nginx"],
                        "header": {"server": "nginx"},
                    }
                ],
                "signatures": [],
            }
        )
        self.assertTrue(
            second.observations.filter(
                entity_type=Observation.EntityType.HTTP,
                lifecycle=Observation.Lifecycle.CHANGED,
            ).exists()
        )

        # Third completed run with empty surface → MISSING then GONE streak.
        third = self._run_with_batch({"hosts": [], "http": [], "signatures": []})
        self.assertTrue(
            third.observations.filter(lifecycle=Observation.Lifecycle.MISSING).exists()
        )

    def test_curiosity_summary_counts_open_ports_and_highlights(self) -> None:
        from datetime import datetime, timedelta, timezone as dt_tz

        soon = (datetime.now(dt_tz.utc) + timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        run = self._run_with_batch(
            {
                "hosts": [
                    {
                        "address": "192.0.2.50",
                        "status": "up",
                        "ports": [
                            {"port": 80, "protocol": "tcp", "state": "open", "service": "http"},
                            {"port": 22, "protocol": "tcp", "state": "open", "service": "ssh"},
                            {"port": 8080, "protocol": "tcp", "state": "open", "service": "http-proxy"},
                        ],
                    }
                ],
                "http": [
                    {
                        "url": "http://192.0.2.50/admin",
                        "status_code": 200,
                        "title": "Admin panel",
                        "tech": ["nginx"],
                        "tls": {
                            "subject_cn": "192.0.2.50",
                            "issuer_cn": "lab",
                            "not_after": soon,
                        },
                    }
                ],
                "signatures": [
                    {
                        "technology": "nginx",
                        "endpoint": "http://192.0.2.50/admin",
                        "confidence": 75,
                        "level": "high",
                    }
                ],
            }
        )
        curiosity = (run.result_summary or {}).get("curiosity") or {}
        self.assertEqual(curiosity.get("hosts_with_open_ports"), 1)
        self.assertEqual(curiosity.get("open_ports_total"), 3)
        self.assertGreaterEqual(curiosity.get("interesting_ports"), 2)
        self.assertGreaterEqual(curiosity.get("admin_or_login_hints"), 1)
        self.assertGreaterEqual(curiosity.get("high_confidence_tech"), 1)
        self.assertGreaterEqual(curiosity.get("expiring_certs"), 1)
        highlight_ids = {item["id"] for item in curiosity.get("highlights") or []}
        self.assertIn("hosts_with_open_ports", highlight_ids)
        self.assertIn("open_ports_total", highlight_ids)
        port_rows = {
            int(o.attrs["port"]): o.attrs.get("curiosity")
            for o in run.observations.filter(entity_type=Observation.EntityType.PORT)
        }
        self.assertEqual(port_rows.get(80), "info")
        self.assertEqual(port_rows.get(22), "high")
        self.assertEqual(port_rows.get(8080), "medium")

    def test_observations_and_diff_api(self) -> None:
        first = self._run_with_batch(
            {
                "hosts": [{"address": "192.0.2.50", "status": "up", "ports": []}],
                "http": [],
                "signatures": [],
            }
        )
        second = self._run_with_batch(
            {
                "hosts": [
                    {
                        "address": "192.0.2.50",
                        "status": "up",
                        "ports": [{"port": 443, "protocol": "tcp", "state": "open"}],
                    }
                ],
                "http": [],
                "signatures": [],
            }
        )
        client = APIClient()
        client.force_login(self.owner)
        response = client.get(reverse("scan-observations", args=[second.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json()["count"], 1)

        response = client.get(
            reverse("scan-diff", args=[second.pk]),
            {"against": first.pk},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreaterEqual(body["counts"]["added"], 1)

    def test_diff_api_rejects_different_host_set(self) -> None:
        first = self._run_with_batch(
            {
                "hosts": [
                    {
                        "address": "192.0.2.50",
                        "status": "up",
                        "ports": [{"port": 80, "protocol": "tcp", "state": "open"}],
                    }
                ]
            }
        )
        other_target = Target.objects.create(
            owner=self.owner,
            address="198.51.100.77",
            target_type=Target.Type.IP,
        )
        other = ScanRun.objects.create(
            owner=self.owner,
            status=ScanRun.Status.COMPLETED,
            finished_at=timezone.now(),
            total_batches=1,
            completed_batches=1,
            progress=100,
        )
        ScanBatch.objects.create(
            run=other,
            target=other_target,
            target_address=other_target.address,
            target_type=other_target.target_type,
            status=ScanBatch.Status.COMPLETED,
            progress=100,
            result={},
            finished_at=timezone.now(),
        )
        client = APIClient()
        client.force_login(self.owner)
        response = client.get(
            reverse("scan-diff", args=[first.pk]),
            {"against": other.pk},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("same group", response.json()["detail"].lower())


class SignatureEngineTests(TestCase):
    def test_load_pack_and_match_nginx(self) -> None:
        sigs = load_signatures()
        self.assertGreaterEqual(len(sigs), 3)
        hits = match_http_records(
            [
                {
                    "url": "https://lab.example/",
                    "status_code": 200,
                    "header": {"server": "nginx/1.24"},
                    "body": "",
                }
            ]
        )
        self.assertTrue(any(h["technology"] == "nginx" for h in hits))
        self.assertTrue(any(h["level"] in {"low", "medium", "high"} for h in hits))

    def test_wordpress_html_signal(self) -> None:
        wordpress = next(
            s for s in load_signatures() if (s.get("metadata") or {}).get("id") == "wordpress-core"
        )
        hit = evaluate_signature(
            wordpress,
            {
                "url": "https://blog.example/",
                "status_code": 200,
                "header": {},
                "body": '<html><link rel="stylesheet" href="/wp-content/themes/x.css"></html>',
            },
        )
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit["technology"], "WordPress")
        self.assertGreaterEqual(hit["confidence"], 20)


class ExportAndCryptoTests(TestCase):
    def setUp(self) -> None:
        self.owner = create_user("analyst", UserProfile.Role.ANALYST)
        self.admin = create_user("admin", UserProfile.Role.ADMIN)
        self.run = ScanRun.objects.create(
            owner=self.owner,
            status=ScanRun.Status.COMPLETED,
            modules_snapshot=[],
            total_batches=1,
            completed_batches=1,
            progress=100,
            finished_at=timezone.now(),
        )
        Observation.objects.create(
            run=self.run,
            target_address="192.0.2.9",
            entity_type=Observation.EntityType.HOST,
            entity_key="host:192.0.2.9",
            lifecycle=Observation.Lifecycle.NEW,
            attrs={"address": "192.0.2.9", "status": "up"},
        )

    def test_export_json_csv(self) -> None:
        client = APIClient()
        client.force_login(self.owner)
        response = client.get(reverse("scan-export", args=[self.run.pk]), {"format": "json"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"surfacex.export.v1", response.content)
        response = client.get(reverse("scan-export", args=[self.run.pk]), {"format": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"entity_key", response.content)

    @override_settings(APP_DATA_KEY="unit-test-app-data-key-32bytes!!")
    def test_seal_roundtrip(self) -> None:
        envelope = seal('{"server":"nginx"}')
        self.assertTrue(envelope.startswith("sx1:"))
        self.assertEqual(open_sealed(envelope), '{"server":"nginx"}')

    def test_audit_list_admin_only(self) -> None:
        from apps.scans.audit import record_audit

        record_audit(
            actor=self.admin,
            action="scan.export",
            summary="test",
            object_type="scan",
            object_id=self.run.pk,
        )
        client = APIClient()
        client.force_login(self.owner)
        self.assertEqual(client.get(reverse("audit-list")).status_code, 403)
        client.force_login(self.admin)
        response = client.get(reverse("audit-list"))
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()["results"]), 1)


class PauseResumeTests(TestCase):
    def setUp(self) -> None:
        self.owner = create_user("ops2", UserProfile.Role.OPERATOR)
        self.target = Target.objects.create(
            owner=self.owner,
            address="192.0.2.77",
            target_type=Target.Type.IP,
        )
        self.client = APIClient()
        self.client.force_login(self.owner)

    @override_settings(WORKER_TOKEN="test-worker-token")
    def test_resume_republishes_paused_batches(self) -> None:
        run = ScanRun.objects.create(
            owner=self.owner,
            status=ScanRun.Status.PARTIAL,
            modules_snapshot=[{"id": "port-scan", "filters": {}}],
            total_batches=1,
            completed_batches=0,
            progress=0,
            resume_available=True,
            finished_at=timezone.now(),
        )
        batch = ScanBatch.objects.create(
            run=run,
            target=self.target,
            target_address=self.target.address,
            target_type=self.target.target_type,
            status=ScanBatch.Status.PAUSED,
            error="Paused: scan window deadline reached.",
            finished_at=timezone.now(),
        )
        old_delivery = str(batch.delivery_id)
        with self.captureOnCommitCallbacks(execute=True):
            with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
                from unittest.mock import patch

                with patch("apps.scans.services.execute_batch.apply_async") as publish:
                    publish.return_value = None
                    response = self.client.post(reverse("scan-resume", args=[run.pk]))
        self.assertEqual(response.status_code, 200)
        batch.refresh_from_db()
        run.refresh_from_db()
        self.assertEqual(batch.status, ScanBatch.Status.QUEUED)
        self.assertNotEqual(str(batch.delivery_id), old_delivery)
        self.assertEqual(run.status, ScanRun.Status.RUNNING)
        self.assertFalse(run.resume_available)

    @override_settings(WORKER_TOKEN="test-worker-token")
    def test_deadline_pause_requests_cancel_and_rejects_late_complete(self) -> None:
        run = ScanRun.objects.create(
            owner=self.owner,
            status=ScanRun.Status.RUNNING,
            modules_snapshot=[{"id": "port-scan", "filters": {}}],
            total_batches=1,
            completed_batches=0,
            progress=10,
            started_at=timezone.now() - timedelta(minutes=5),
            deadline_at=timezone.now() - timedelta(seconds=5),
        )
        batch = ScanBatch.objects.create(
            run=run,
            target=self.target,
            target_address=self.target.address,
            target_type=self.target.target_type,
            status=ScanBatch.Status.RUNNING,
            progress=40,
            claimed_at=timezone.now() - timedelta(minutes=2),
        )
        headers = {"HTTP_X_WORKER_TOKEN": "test-worker-token"}
        identity = {"delivery_id": str(batch.delivery_id)}

        response = self.client.get(
            reverse("internal-batch-cancel", args=[batch.pk]),
            identity,
            **headers,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["cancel_requested"])
        self.assertEqual(body["status"], ScanBatch.Status.PAUSED)
        batch.refresh_from_db()
        self.assertEqual(batch.status, ScanBatch.Status.PAUSED)

        # Worker kill acknowledgement must leave the batch PAUSED for resume.
        response = self.client.post(
            reverse("internal-batch-fail", args=[batch.pk]),
            {**identity, "error": "Scan cancelled", "cancelled": True},
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 200)
        batch.refresh_from_db()
        self.assertEqual(batch.status, ScanBatch.Status.PAUSED)

        # Late complete after deadline must not revive work.
        response = self.client.post(
            reverse("internal-batch-complete", args=[batch.pk]),
            {
                **identity,
                "result": {"hosts": [{"address": self.target.address, "ports": []}]},
            },
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 409)
        batch.refresh_from_db()
        self.assertEqual(batch.status, ScanBatch.Status.PAUSED)
