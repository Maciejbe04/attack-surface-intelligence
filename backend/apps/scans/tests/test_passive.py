from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import UserProfile
from apps.scans.models import Observation, ScanBatch, ScanRun, Target
from apps.scans.modules import validate_modules
from apps.scans.normalize import extract_observation_rows
from apps.scans.passive import (
    PassiveDiscoveryInputError,
    PassiveProviderError,
    discover_passive,
    normalize_passive_query,
    query_crt_sh,
    summarize_rdap,
)


TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}


def create_user(username: str, role: str) -> User:
    user = User.objects.create_user(username=username, password="test-password")
    UserProfile.objects.create(user=user, role=role)
    return user


@override_settings(CACHES=TEST_CACHES)
class PassiveDiscoveryTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.operator = create_user("passive-operator", UserProfile.Role.OPERATOR)
        self.viewer = create_user("passive-viewer", UserProfile.Role.VIEWER)
        self.client = APIClient()

    def test_query_normalization_accepts_domain_and_ip(self) -> None:
        self.assertEqual(
            normalize_passive_query(" WWW.Example.COM. "),
            ("domain", "www.example.com"),
        )
        self.assertEqual(
            normalize_passive_query("2001:0db8::1"),
            ("ip", "2001:db8::1"),
        )
        for invalid in ("", "localhost", "https://example.com", "bad_domain.test"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(PassiveDiscoveryInputError):
                    normalize_passive_query(invalid)

    @patch("apps.scans.passive._get_json")
    def test_crt_sh_normalizes_deduplicates_and_limits_scope(self, get_json) -> None:
        get_json.return_value = [
            {"name_value": "*.example.com\nwww.example.com"},
            {"name_value": "WWW.Example.COM"},
            {"name_value": "other.example.org"},
            {"name_value": "api.example.com"},
        ]
        self.assertEqual(
            query_crt_sh("example.com"),
            ["api.example.com", "example.com", "www.example.com"],
        )

    def test_rdap_summary_extracts_owner_network_and_asn(self) -> None:
        summary = summarize_rdap(
            {
                "handle": "NET-192-0-2-0-1",
                "name": "EXAMPLE-NET",
                "country": "pl",
                "startAddress": "192.0.2.0",
                "endAddress": "192.0.2.255",
                "arin_originas0_originautnums": [64500],
                "nameservers": [{"ldhName": "ns1.example.com"}],
                "entities": [
                    {
                        "vcardArray": [
                            "vcard",
                            [["fn", {}, "text", "Example Org"]],
                        ]
                    }
                ],
            },
            "ip",
        )
        self.assertEqual(summary["handle"], "NET-192-0-2-0-1")
        self.assertEqual(summary["name"], "EXAMPLE-NET")
        self.assertEqual(summary["country"], "PL")
        self.assertEqual(summary["network"], "192.0.2.0 – 192.0.2.255")
        self.assertEqual(summary["asns"], [64500])
        self.assertEqual(summary["nameservers"], [])

    @patch("apps.scans.passive.query_rdap")
    @patch("apps.scans.passive.query_crt_sh")
    def test_discover_passive_partial_failure_and_cache(
        self,
        query_crt,
        query_rdap,
    ) -> None:
        query_crt.return_value = ["www.example.com"]
        query_rdap.side_effect = PassiveProviderError("HTTP 500")

        first = discover_passive("example.com")
        self.assertEqual(first["query"], "example.com")
        self.assertEqual(first["subdomains"], ["www.example.com"])
        self.assertIsNone(first["rdap"])
        self.assertEqual(first["sources"]["crt_sh"], "ok")
        self.assertEqual(first["sources"]["rdap"], "error")
        self.assertFalse(first["cached"])
        self.assertTrue(any(item.startswith("rdap:") for item in first["warnings"]))

        second = discover_passive("example.com")
        self.assertTrue(second["cached"])
        self.assertEqual(query_crt.call_count, 1)
        self.assertEqual(query_rdap.call_count, 1)

    def test_api_rbac_and_validation(self) -> None:
        url = reverse("passive-discover")
        self.client.force_login(self.viewer)
        response = self.client.post(url, {"query": "example.com"}, format="json")
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.operator)
        response = self.client.post(url, {"query": ""}, format="json")
        self.assertEqual(response.status_code, 400)

        with patch(
            "apps.scans.views.discover_passive",
            return_value={
                "query": "example.com",
                "type": "domain",
                "subdomains": ["www.example.com"],
                "rdap": None,
                "sources": {"crt_sh": "ok", "rdap": "error"},
                "warnings": ["rdap: HTTP 500"],
                "cached": False,
            },
        ):
            response = self.client.post(url, {"query": "example.com"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["subdomains"], ["www.example.com"])

    def test_passive_discovery_module_validation(self) -> None:
        modules = validate_modules(
            [{"id": "passive-discovery", "filters": {"includeCrt": False}}]
        )
        self.assertEqual(modules[0]["id"], "passive-discovery")
        self.assertFalse(modules[0]["filters"]["includeCrt"])
        self.assertTrue(modules[0]["filters"]["includeRdap"])

    def test_normalize_maps_passive_payload_to_host_observation(self) -> None:
        owner = self.operator
        target = Target.objects.create(
            owner=owner,
            address="example.com",
            target_type=Target.Type.DOMAIN,
        )
        run = ScanRun.objects.create(
            owner=owner,
            status=ScanRun.Status.RUNNING,
            modules_snapshot=[{"id": "passive-discovery", "filters": {}}],
        )
        batch = ScanBatch.objects.create(
            run=run,
            target=target,
            target_address="example.com",
            status=ScanBatch.Status.COMPLETED,
            result={},
        )
        rows = extract_observation_rows(
            batch,
            {
                "hosts": [],
                "http": [],
                "signatures": [],
                "passive": {
                    "query": "example.com",
                    "type": "domain",
                    "subdomains": ["api.example.com", "www.example.com"],
                    "rdap": {
                        "handle": "D1",
                        "name": "Example Org",
                        "country": "US",
                        "network": "",
                        "asns": [64500],
                        "nameservers": ["ns1.example.com"],
                    },
                    "sources": {"crt_sh": "ok", "rdap": "ok"},
                    "warnings": [],
                },
            },
        )
        passive_rows = [row for row in rows if row["entity_key"] == "passive:example.com"]
        self.assertEqual(len(passive_rows), 1)
        self.assertEqual(passive_rows[0]["entity_type"], Observation.EntityType.HOST)
        self.assertEqual(passive_rows[0]["attrs"]["subdomain_count"], 2)
        self.assertEqual(passive_rows[0]["attrs"]["rdap_name"], "Example Org")
        self.assertEqual(passive_rows[0]["attrs"]["asns"], [64500])
        self.assertEqual(passive_rows[0]["evidence"][0]["kind"], "passive")
