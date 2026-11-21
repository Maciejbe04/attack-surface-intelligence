from __future__ import annotations

import socket
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import UserProfile
from apps.scans import runner, scope
from apps.scans.models import ScanBatch, ScanRun, Target
from apps.scans.modules import validate_modules
from apps.scans.runner import ScanRunnerError, _nmap_arguments, _parse_httpx, _parse_nmap, execute_scan


def selected(*module_ids: str, **filters) -> dict:
    modules = validate_modules([{"id": module_id, "filters": filters.get(module_id, {})} for module_id in module_ids])
    return runner._module_map(modules)


def fake_resolver(mapping: dict[str, list[str]]):
    def resolve(host, port, proto=0):
        if host not in mapping:
            raise socket.gaierror("not found")
        return [(socket.AF_INET, socket.SOCK_STREAM, proto, "", (ip, 0)) for ip in mapping[host]]

    return resolve


class LivenessTests(SimpleTestCase):
    def test_ranges_use_host_discovery_not_pn(self):
        with patch("apps.scans.runner._supports_syn_scan", return_value=False):
            arguments, _ = _nmap_arguments("192.0.2.0/24", "cidr", selected("port-scan"))
        self.assertNotIn("-Pn", arguments)
        self.assertIn("-PE", arguments)
        self.assertTrue(any(item.startswith("-PS") for item in arguments))

    def test_range_discovery_follows_host_discovery_filters(self):
        filters = {"host-discovery": {"method": "tcp", "tcpPorts": "8443"}}
        with patch("apps.scans.runner._supports_syn_scan", return_value=False):
            arguments, _ = _nmap_arguments(
                "192.0.2.0/24", "cidr", selected("host-discovery", "port-scan", **filters)
            )
        self.assertIn("-PS8443", arguments)
        self.assertNotIn("-PE", arguments)

    def test_single_host_still_probed_with_pn(self):
        with patch("apps.scans.runner._supports_syn_scan", return_value=False):
            arguments, _ = _nmap_arguments("192.0.2.5", "ip", selected("port-scan"))
        self.assertIn("-Pn", arguments)

    def test_parser_drops_hosts_up_only_because_of_pn(self):
        xml = b"""<nmaprun>
          <host><status state="up" reason="user-set"/><address addr="192.0.2.1"/></host>
          <host><status state="up" reason="user-set"/><address addr="192.0.2.2"/>
            <ports><port protocol="tcp" portid="22"><state state="open"/><service name="ssh"/></port></ports></host>
          <host><status state="up" reason="echo-reply"/><address addr="192.0.2.3"/></host>
          <host><status state="down" reason="no-response"/><address addr="192.0.2.4"/></host>
        </nmaprun>"""
        addresses = [host["address"] for host in _parse_nmap(xml)]
        self.assertEqual(addresses, ["192.0.2.2", "192.0.2.3"])


class ScopeTests(SimpleTestCase):
    def test_no_scope_configured_allows_everything(self):
        scope.check_target("8.8.8.8", "ip")

    @override_settings(SCAN_ALLOWED_NETWORKS="10.0.0.0/8, 192.168.56.0/24", SCAN_ALLOWED_DOMAINS="")
    def test_networks(self):
        scope.check_target("10.1.2.3", "ip")
        scope.check_target("10.20.0.0/16", "cidr")
        scope.check_target("192.168.56.0/25", "cidr")
        for address, kind in (("8.8.8.8", "ip"), ("192.168.0.0/16", "cidr"), ("2001:db8::1", "ip")):
            with self.assertRaises(scope.OutOfScope):
                scope.check_target(address, kind)

    @override_settings(SCAN_ALLOWED_NETWORKS="", SCAN_ALLOWED_DOMAINS="lab.agh.test")
    def test_domain_suffixes(self):
        scope.check_target("lab.agh.test", "domain")
        scope.check_target("app.lab.agh.test", "domain")
        for domain in ("evillab.agh.test", "agh.test", "example.com"):
            with self.assertRaises(scope.OutOfScope):
                scope.check_target(domain, "domain")

    @override_settings(SCAN_ALLOWED_NETWORKS="10.0.0.0/8", SCAN_ALLOWED_DOMAINS="lab.agh.test")
    def test_domain_must_resolve_inside_networks_at_scan_time(self):
        resolver = fake_resolver(
            {"in.lab.agh.test": ["10.0.0.5"], "out.lab.agh.test": ["10.0.0.5", "203.0.113.9"]}
        )
        scope.check_target("in.lab.agh.test", "domain", resolve=True, resolver=resolver)
        with self.assertRaises(scope.OutOfScope):
            scope.check_target("out.lab.agh.test", "domain", resolve=True, resolver=resolver)
        with self.assertRaises(scope.OutOfScope):
            scope.check_target("missing.lab.agh.test", "domain", resolve=True, resolver=resolver)

    def test_split_into_batches(self):
        self.assertEqual(len(scope.split_into_batches("10.0.0.0/16", "cidr")), 256)
        self.assertEqual(scope.split_into_batches("10.0.0.0/16", "cidr")[1], "10.0.1.0/24")
        self.assertEqual(scope.split_into_batches("10.0.0.0/26", "cidr"), ["10.0.0.0/26"])
        self.assertEqual(scope.split_into_batches("10.0.0.1", "ip"), ["10.0.0.1"])
        self.assertEqual(scope.split_into_batches("app.example.test", "domain"), ["app.example.test"])

    @override_settings(SCAN_ALLOWED_NETWORKS="10.0.0.0/8")
    def test_worker_refuses_out_of_scope_target(self):
        modules = validate_modules([{"id": "port-scan", "filters": {}}])
        with patch("apps.scans.runner._run_command") as run_command, self.assertRaises(ScanRunnerError):
            execute_scan(
                {"target": {"address": "203.0.113.7", "type": "ip"}, "modules": modules},
                should_cancel=lambda: False,
                report_progress=lambda progress, message="": None,
            )
        run_command.assert_not_called()


class HttpEvidenceTests(SimpleTestCase):
    def test_httpx_records_headers_favicon_and_redirect_without_following(self):
        arguments = runner._httpx_arguments(selected("http-fingerprint"))
        for flag in ("-include-response-header", "-favicon", "-location"):
            self.assertIn(flag, arguments)
        self.assertNotIn("-follow-redirects", arguments)

    def test_cookie_values_and_bodies_are_not_stored(self):
        line = (
            b'{"url":"https://192.0.2.5","status_code":302,"location":"/login","favicon":"-123",'
            b'"body":"<html>secret</html>","header":{"Server":"nginx","x_powered_by":"PHP/8.1",'
            b'"set_cookie":["PHPSESSID=abc123secret; path=/; HttpOnly","csrf=t0k3n; Secure; SameSite=Strict"]}}\n'
        )
        record = _parse_httpx(line)[0]
        self.assertEqual(record["headers"]["server"], "nginx")
        self.assertEqual(record["headers"]["x-powered-by"], "PHP/8.1")
        self.assertEqual(record["location"], "/login")
        self.assertEqual(
            record["cookies"],
            [
                {"name": "PHPSESSID", "secure": False, "httponly": True, "samesite": ""},
                {"name": "csrf", "secure": True, "httponly": False, "samesite": "Strict"},
            ],
        )
        serialized = str(record)
        for secret in ("abc123secret", "t0k3n", "<html>"):
            self.assertNotIn(secret, serialized)
        self.assertNotIn("body", record)


class BatchSplittingApiTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user("op", password="test-password")
        UserProfile.objects.create(user=self.operator, role=UserProfile.Role.OPERATOR)
        self.client = APIClient()
        self.client.force_authenticate(self.operator)

    def create_target(self, address, kind="cidr"):
        return Target.objects.create(owner=self.operator, address=address, target_type=kind)

    def scan(self, *targets):
        return self.client.post(
            reverse("scan-list"),
            {"target_ids": [target.id for target in targets], "modules": [{"id": "port-scan", "filters": {}}]},
            format="json",
        )

    def test_large_range_becomes_one_batch_per_subnet(self):
        response = self.scan(self.create_target("10.0.0.0/22"), self.create_target("10.9.9.9", "ip"))
        self.assertEqual(response.status_code, 201, response.content)
        run = ScanRun.objects.get()
        self.assertEqual(run.total_batches, 5)
        self.assertEqual(
            sorted(ScanBatch.objects.values_list("target_address", flat=True)),
            ["10.0.0.0/24", "10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24", "10.9.9.9"],
        )

    @override_settings(SCAN_MAX_BATCHES_PER_RUN=3)
    def test_too_many_batches_rejected(self):
        response = self.scan(self.create_target("10.0.0.0/22"))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ScanRun.objects.exists())

    def test_slash16_accepted_as_target(self):
        response = self.client.post(
            reverse("target-list"), {"address": "10.20.0.0/16", "type": "cidr"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)

    @override_settings(SCAN_ALLOWED_NETWORKS="10.0.0.0/8")
    def test_target_outside_scope_rejected_on_save(self):
        response = self.client.post(reverse("target-list"), {"address": "8.8.8.8", "type": "ip"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("scope", str(response.content))


class ImportScopeTests(TestCase):
    @override_settings(SCAN_ALLOWED_NETWORKS="10.0.0.0/8")
    def test_import_rejects_lines_outside_scope(self):
        from apps.scans.import_targets import parse_import_payload

        result = parse_import_payload(filename="hosts.txt", raw=b"10.0.0.1\n8.8.8.8\n10.1.0.0/16\n")
        self.assertEqual(sorted(target.address for target in result.targets), ["10.0.0.1", "10.1.0.0/16"])
        self.assertTrue(any("8.8.8.8" in error and "scope" in error for error in result.errors))
