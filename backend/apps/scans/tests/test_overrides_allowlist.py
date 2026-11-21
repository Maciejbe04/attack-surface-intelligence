from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import UserProfile
from apps.scans.allowlist import assert_resolvable_allowed, is_value_allowed
from apps.scans.models import AllowlistEntry, ManualOverride, Observation, ScanRun, Target
from apps.scans.overrides import effective_attrs, notes_plaintext


def make_user(username: str, role: str = UserProfile.Role.ADMIN) -> User:
    user = User.objects.create_user(username=username, password="test-password")
    UserProfile.objects.create(user=user, role=role)
    return user


class AllowlistTests(TestCase):
    def setUp(self) -> None:
        self.user = make_user("op")
        self.client = APIClient()
        self.client.force_login(self.user)

    def test_empty_allowlist_is_open(self) -> None:
        self.assertTrue(is_value_allowed(self.user, "192.0.2.1", "ip"))

    def test_cidr_and_domain_enforced(self) -> None:
        AllowlistEntry.objects.create(
            owner=self.user, value="192.0.2.0/24", entry_type="cidr"
        )
        AllowlistEntry.objects.create(
            owner=self.user, value="example.test", entry_type="domain"
        )
        self.assertTrue(is_value_allowed(self.user, "192.0.2.10", "ip"))
        self.assertFalse(is_value_allowed(self.user, "198.51.100.1", "ip"))
        self.assertTrue(is_value_allowed(self.user, "www.example.test", "domain"))
        self.assertFalse(is_value_allowed(self.user, "evil.test", "domain"))

    def test_target_create_rejected_when_outside(self) -> None:
        AllowlistEntry.objects.create(
            owner=self.user, value="192.0.2.0/24", entry_type="cidr"
        )
        response = self.client.post(
            reverse("target-list"),
            {"address": "198.51.100.9", "type": "ip"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_scan_rejected_when_outside(self) -> None:
        AllowlistEntry.objects.create(
            owner=self.user, value="192.0.2.0/24", entry_type="cidr"
        )
        Target.objects.create(owner=self.user, address="198.51.100.9", target_type="ip")
        # Create while allowlist empty was skipped — target exists from before enforce;
        # scan must still reject.
        target = Target.objects.get(address="198.51.100.9")
        response = self.client.post(
            reverse("scan-list"),
            {
                "target_ids": [target.id],
                "modules": [{"id": "host-discovery", "filters": {}}],
                "client_request_id": "allowlist-scan-1",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_domain_allowlist_allows_cdn_ips(self) -> None:
        AllowlistEntry.objects.create(
            owner=self.user, value="onet.pl", entry_type="domain"
        )
        with patch(
            "apps.scans.allowlist.resolve_ips",
            return_value=["13.249.8.126", "52.85.154.72"],
        ):
            resolved = assert_resolvable_allowed(self.user, "onet.pl", "domain")
        self.assertEqual(resolved, ["13.249.8.126", "52.85.154.72"])

    def test_domain_allowlist_tolerates_dns_failure(self) -> None:
        import socket

        AllowlistEntry.objects.create(
            owner=self.user, value="onet.pl", entry_type="domain"
        )
        with patch(
            "apps.scans.allowlist.resolve_ips",
            side_effect=socket.gaierror(-3, "Temporary failure in name resolution"),
        ):
            resolved = assert_resolvable_allowed(self.user, "onet.pl", "domain")
        self.assertEqual(resolved, [])

    def test_domain_plus_cidr_enforces_resolved_ip(self) -> None:
        AllowlistEntry.objects.create(
            owner=self.user, value="onet.pl", entry_type="domain"
        )
        AllowlistEntry.objects.create(
            owner=self.user, value="192.0.2.0/24", entry_type="cidr"
        )
        with patch(
            "apps.scans.allowlist.resolve_ips",
            return_value=["198.51.100.9"],
        ):
            with self.assertRaises(Exception) as ctx:
                assert_resolvable_allowed(self.user, "onet.pl", "domain")
        self.assertIn("outside allowlist", str(ctx.exception))


class OverrideTests(TestCase):
    def setUp(self) -> None:
        self.user = make_user("analyst", UserProfile.Role.ANALYST)
        self.client = APIClient()
        self.client.force_login(self.user)
        self.run = ScanRun.objects.create(owner=self.user, status=ScanRun.Status.COMPLETED)
        self.obs = Observation.objects.create(
            run=self.run,
            target_address="192.0.2.1",
            entity_type=Observation.EntityType.TECH,
            entity_key="tech:192.0.2.1:80:wordpress",
            attrs={"technology": "wordpress", "confidence": "medium"},
            lifecycle=Observation.Lifecycle.NEW,
        )

    def test_override_survives_and_merges(self) -> None:
        response = self.client.post(
            reverse("override-upsert"),
            {
                "entity_key": self.obs.entity_key,
                "target_address": "192.0.2.1",
                "tags": ["cms", "reviewed"],
                "notes": "False positive — custom app",
                "attrs_patch": {"technology": "custom-app", "confidence": "high"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        override = ManualOverride.objects.get(owner=self.user, entity_key=self.obs.entity_key)
        self.assertEqual(notes_plaintext(override), "False positive — custom app")
        merged = effective_attrs(self.obs.attrs, override)
        self.assertEqual(merged["technology"], "custom-app")

        # New run / new observation with same entity_key still sees override via API.
        run2 = ScanRun.objects.create(owner=self.user, status=ScanRun.Status.COMPLETED)
        Observation.objects.create(
            run=run2,
            target_address="192.0.2.1",
            entity_type=Observation.EntityType.TECH,
            entity_key=self.obs.entity_key,
            attrs={"technology": "wordpress", "confidence": "medium"},
            lifecycle=Observation.Lifecycle.UNCHANGED,
        )
        listed = self.client.get(reverse("scan-observations", args=[run2.id]))
        self.assertEqual(listed.status_code, 200)
        row = listed.json()["results"][0]
        self.assertEqual(row["effective_attrs"]["technology"], "custom-app")
        self.assertEqual(row["tags"], ["cms", "reviewed"])
        self.assertIn("False positive", row["notes"])
