from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import UserProfile
from apps.scans.models import ScanRun, Target
from apps.scans.import_targets import parse_import_payload


def create_user(username: str, role: str) -> User:
    user = User.objects.create_user(username=username, password="test-password")
    UserProfile.objects.create(user=user, role=role)
    return user


class TargetImportParseTests(TestCase):
    def test_plaintext_and_csv_and_json(self) -> None:
        plain = parse_import_payload(
            filename="hosts.txt",
            raw=b"10.0.0.1\n# comment\napp.example.lab\n10.0.0.1\n",
        )
        self.assertEqual(len(plain.targets), 2)
        self.assertGreaterEqual(plain.skipped_duplicates_in_file, 1)

        csv_payload = parse_import_payload(
            filename="hosts.csv",
            raw=b"value,type,comment\n10.0.0.2,ip,lab\n10.0.0.0/30,cidr,range\n",
        )
        self.assertEqual(len(csv_payload.targets), 2)

        json_payload = parse_import_payload(
            filename="hosts.json",
            raw=b'{"schema_version":1,"targets":[{"value":"10.0.0.3","type":"ip"}]}',
        )
        self.assertEqual(json_payload.targets[0].address, "10.0.0.3")


class TargetImportAPITests(TestCase):
    def setUp(self) -> None:
        self.operator = create_user("import-op", UserProfile.Role.OPERATOR)
        self.client = APIClient()
        self.client.force_login(self.operator)

    def test_import_file_creates_targets_and_queues_scan(self) -> None:
        upload = SimpleUploadedFile(
            "hosts.txt",
            b"192.0.2.10\n192.0.2.11\nnot a host!!\n",
            content_type="text/plain",
        )
        with patch("apps.scans.services.execute_batch.apply_async") as publish:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    reverse("target-import"),
                    {
                        "file": upload,
                        "start_scan": "true",
                        "client_request_id": "import-1",
                    },
                    format="multipart",
                )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["created_count"], 2)
        self.assertEqual(payload["total_count"], 2)
        self.assertTrue(payload["parse_errors"])
        self.assertIsNotNone(payload["scan"])
        self.assertEqual(ScanRun.objects.count(), 1)
        self.assertEqual(Target.objects.filter(owner=self.operator).count(), 2)
        self.assertEqual(publish.call_count, 2)

    def test_import_without_autoscan_only_stores_targets(self) -> None:
        upload = SimpleUploadedFile(
            "hosts.txt",
            b"192.0.2.20\n",
            content_type="text/plain",
        )
        response = self.client.post(
            reverse("target-import"),
            {"file": upload, "start_scan": "false"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.json()["scan"])
        self.assertEqual(ScanRun.objects.count(), 0)
        self.assertEqual(Target.objects.count(), 1)
