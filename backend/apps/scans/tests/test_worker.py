from __future__ import annotations

import json
import urllib.error
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.scans.modules import validate_modules
from apps.scans.runner import _run_command, execute_scan
from apps.scans.tasks import _api_request, execute_batch, reconcile_batches


NMAP_XML = b"""<?xml version="1.0"?>
<nmaprun>
  <host>
    <status state="up"/>
    <address addr="192.0.2.50" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="443">
        <state state="open"/>
        <service name="https" product="Example Server" version="1.0"/>
      </port>
    </ports>
  </host>
</nmaprun>
"""


class RunnerTests(SimpleTestCase):
    def test_pipeline_uses_argument_lists_and_normalizes_results(self) -> None:
        modules = validate_modules([{"id": "full-pipeline", "filters": {}}])
        outputs = [
            (NMAP_XML, b""),
            (
                b'{"url":"https://192.0.2.50:443","status_code":200,'
                b'"tech":["ExampleTech"]}\n',
                b"",
            ),
        ]
        commands: list[list[str]] = []

        def fake_run(arguments, **kwargs):
            commands.append(arguments)
            return outputs.pop(0)

        with (
            patch("apps.scans.runner._run_command", side_effect=fake_run),
            patch("apps.scans.runner._supports_syn_scan", return_value=False),
        ):
            result = execute_scan(
                {
                    "target": {"address": "192.0.2.50", "type": "ip"},
                    "modules": modules,
                },
                should_cancel=lambda: False,
                report_progress=lambda progress, message="": None,
            )

        self.assertEqual(commands[0][0], "nmap")
        self.assertIn("-sT", commands[0])
        self.assertEqual(commands[1][0], "httpx")
        self.assertNotIn("-follow-redirects", commands[1])
        self.assertEqual(result["hosts"][0]["ports"][0]["port"], 443)
        self.assertEqual(result["signatures"][0]["technology"], "ExampleTech")

    def test_http_probe_preserves_saved_domain_for_vhost_and_tls_sni(self) -> None:
        modules = validate_modules([{"id": "http-fingerprint", "filters": {}}])
        httpx_inputs: list[bytes] = []

        def fake_run(arguments, **kwargs):
            if arguments[0] == "nmap":
                return NMAP_XML, b""
            httpx_inputs.append(kwargs["input_data"])
            return b"", b""

        with (
            patch("apps.scans.runner._run_command", side_effect=fake_run),
            patch("apps.scans.runner._supports_syn_scan", return_value=False),
        ):
            execute_scan(
                {
                    "target": {"address": "app.example.test", "type": "domain"},
                    "modules": modules,
                },
                should_cancel=lambda: False,
                report_progress=lambda progress, message="": None,
            )

        self.assertEqual(httpx_inputs, [b"https://app.example.test:443\n"])

    def test_subprocess_is_started_without_a_shell(self) -> None:
        process = Mock()
        process.poll.return_value = 0
        process.returncode = 0

        def fake_popen(arguments, **kwargs):
            kwargs["stdout"].write(b"ok")
            return process

        with patch("apps.scans.runner.subprocess.Popen", side_effect=fake_popen) as popen:
            output, error = _run_command(
                ["nmap", "-sn", "192.0.2.1"],
                input_data=None,
                should_cancel=lambda: False,
            )

        self.assertEqual(output, b"ok")
        self.assertEqual(error, b"")
        arguments = popen.call_args.args[0]
        self.assertIsInstance(arguments, list)
        self.assertFalse(popen.call_args.kwargs["shell"])
        self.assertTrue(popen.call_args.kwargs["start_new_session"])


@override_settings(
    API_INTERNAL_URL="http://api:8000",
    WORKER_TOKEN="worker-test-token",
)
class CeleryTaskTests(SimpleTestCase):
    def test_reconciler_requests_recovery_through_internal_api(self) -> None:
        with (
            patch(
                "apps.scans.tasks._get_broker_epoch",
                return_value="broker-epoch-1",
            ),
            patch(
                "apps.scans.tasks._api_request",
                return_value={
                    "epoch_changed": False,
                    "recovered": 2,
                    "published": 2,
                    "failed": 0,
                },
            ) as api_request,
        ):
            result = reconcile_batches.run()

        self.assertEqual(result["published"], 2)
        api_request.assert_called_once_with(
            "POST",
            "/api/internal/batches/reconcile/",
            {"broker_epoch": "broker-epoch-1"},
        )

    def test_task_uses_internal_api_and_posts_completion(self) -> None:
        calls: list[tuple[str, str, object]] = []

        def fake_api(method, path, payload=None):
            calls.append((method, path, payload))
            if path.endswith("/claim/"):
                return {
                    "terminal": False,
                    "target": {"address": "192.0.2.60", "type": "ip"},
                    "modules": [],
                }
            return {}

        with (
            patch("apps.scans.tasks._api_request", side_effect=fake_api),
            patch(
                "apps.scans.tasks.execute_scan",
                return_value={"target": "192.0.2.60"},
            ),
        ):
            result = execute_batch.run(7, "delivery-7")

        self.assertEqual(result, {"status": "completed"})
        self.assertEqual(calls[0][1], "/api/internal/batches/7/claim/")
        self.assertEqual(calls[-1][1], "/api/internal/batches/7/complete/")
        self.assertEqual(
            calls[-1][2],
            {
                "delivery_id": "delivery-7",
                "result": {"target": "192.0.2.60"},
            },
        )

    def test_internal_api_retries_transient_failures(self) -> None:
        response = Mock()
        response.read.return_value = json.dumps({"ok": True}).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)

        with (
            patch(
                "apps.scans.tasks.urllib.request.urlopen",
                side_effect=[
                    urllib.error.URLError("temporary"),
                    TimeoutError("temporary"),
                    response,
                ],
            ) as urlopen,
            patch("apps.scans.tasks.time.sleep"),
        ):
            result = _api_request("GET", "/api/internal/example/")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(urlopen.call_count, 3)
