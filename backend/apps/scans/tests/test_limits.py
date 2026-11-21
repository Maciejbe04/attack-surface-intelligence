from __future__ import annotations

from unittest.mock import patch

from celery.exceptions import SoftTimeLimitExceeded
from django.test import SimpleTestCase, override_settings

from apps.scans import runner
from apps.scans.modules import validate_modules
from apps.scans.runner import ScanLimits, _httpx_arguments, _nmap_arguments, execute_scan
from apps.scans.tasks import execute_batch

NMAP_XML = b"""<?xml version="1.0"?><nmaprun><host><status state="up"/>
<address addr="192.0.2.50" addrtype="ipv4"/><ports><port protocol="tcp" portid="443">
<state state="open"/><service name="https"/></port></ports></host></nmaprun>"""

LIMITS = ScanLimits(max_rate_total=300, http_rate_total=100, worker_slots=2, batch_time_budget=240)


def _value_after(arguments: list[str], flag: str) -> str:
    return arguments[arguments.index(flag) + 1]


class GlobalRateLimitTests(SimpleTestCase):
    def test_user_rate_is_capped_by_global_share(self):
        modules = validate_modules([{"id": "port-scan", "filters": {"maxRate": 5000}}])
        with patch("apps.scans.runner._supports_syn_scan", return_value=False):
            arguments, _ = _nmap_arguments("192.0.2.1", "ip", runner._module_map(modules), limits=LIMITS)
        self.assertEqual(_value_after(arguments, "--max-rate"), "150")

    def test_lower_user_rate_is_kept(self):
        modules = validate_modules([{"id": "port-scan", "filters": {"maxRate": 20}}])
        with patch("apps.scans.runner._supports_syn_scan", return_value=False):
            arguments, _ = _nmap_arguments("192.0.2.1", "ip", runner._module_map(modules), limits=LIMITS)
        self.assertEqual(_value_after(arguments, "--max-rate"), "20")

    def test_host_discovery_is_rate_limited_too(self):
        modules = validate_modules([{"id": "host-discovery", "filters": {}}])
        arguments, _ = _nmap_arguments("192.0.2.0/28", "cidr", runner._module_map(modules), limits=LIMITS)
        self.assertIn("-sn", arguments)
        self.assertEqual(_value_after(arguments, "--max-rate"), "150")

    def test_httpx_rate_and_threads_capped(self):
        modules = validate_modules([{"id": "http-fingerprint", "filters": {"rateLimit": 500}}])
        arguments = _httpx_arguments(runner._module_map(modules), LIMITS)
        self.assertEqual(_value_after(arguments, "-rate-limit"), "50")
        self.assertEqual(_value_after(arguments, "-threads"), "50")
        tiny = ScanLimits(http_rate_total=10, worker_slots=4)
        arguments = _httpx_arguments(runner._module_map(modules), tiny)
        self.assertEqual(_value_after(arguments, "-rate-limit"), "2")
        self.assertEqual(_value_after(arguments, "-threads"), "2")

    @override_settings(SCAN_MAX_RATE_TOTAL=90, SCAN_HTTP_RATE_TOTAL=30, SCAN_WORKER_SLOTS=3, SCAN_BATCH_TIME_BUDGET=100)
    def test_limits_read_from_settings(self):
        limits = ScanLimits.from_settings()
        self.assertEqual((limits.nmap_rate_per_slot, limits.http_rate_per_slot), (30, 10))
        self.assertEqual(limits.batch_time_budget, 100)


class TimeBudgetTests(SimpleTestCase):
    def run_scan(self, limits, durations):
        clock = {"now": 1000.0}
        commands: list[tuple[list[str], int]] = []

        def fake_run(arguments, **kwargs):
            commands.append((arguments, kwargs["timeout"]))
            clock["now"] += durations.pop(0)
            if arguments[0] == "nmap":
                return NMAP_XML, b""
            return b'{"url":"https://192.0.2.50:443"}\n', b""

        modules = validate_modules([{"id": "full-pipeline", "filters": {}}])
        with (
            patch("apps.scans.runner._run_command", side_effect=fake_run),
            patch("apps.scans.runner._supports_syn_scan", return_value=False),
            patch("apps.scans.runner.time.monotonic", side_effect=lambda: clock["now"]),
        ):
            result = execute_scan(
                {"target": {"address": "192.0.2.50", "type": "ip"}, "modules": modules},
                should_cancel=lambda: False,
                report_progress=lambda progress, message="": None,
                limits=limits,
            )
        return result, commands

    def test_commands_fit_inside_batch_budget(self):
        result, commands = self.run_scan(LIMITS, [30, 5])
        (nmap_args, nmap_timeout), (httpx_args, httpx_timeout) = commands
        self.assertLessEqual(nmap_timeout, LIMITS.batch_time_budget - int(LIMITS.batch_time_budget * 0.3))
        # nmap really took 30 s; httpx may only use what is left of the budget.
        self.assertLessEqual(30 + httpx_timeout, LIMITS.batch_time_budget)
        self.assertIn("--host-timeout", nmap_args)
        self.assertEqual(result["metadata"]["http_skipped"], "")
        self.assertEqual(result["metadata"]["limits"]["nmap_max_rate"], 150)

    def test_worst_case_both_commands_use_full_timeouts(self):
        nmap_cap = LIMITS.batch_time_budget - int(LIMITS.batch_time_budget * 0.3)
        _, commands = self.run_scan(LIMITS, [nmap_cap, 0])
        (_, nmap_timeout), (_, httpx_timeout) = commands
        self.assertEqual(nmap_timeout, nmap_cap)
        self.assertLessEqual(nmap_timeout + httpx_timeout, LIMITS.batch_time_budget)

    def test_http_phase_skipped_when_budget_is_spent(self):
        limits = ScanLimits(batch_time_budget=60)
        result, commands = self.run_scan(limits, [58])
        self.assertEqual(len(commands), 1)
        self.assertIn("time budget", result["metadata"]["http_skipped"])
        self.assertEqual(result["hosts"][0]["ports"][0]["port"], 443)

    def test_total_never_exceeds_celery_soft_limit(self):
        from django.conf import settings

        self.assertLess(settings.SCAN_BATCH_TIME_BUDGET, settings.CELERY_TASK_SOFT_TIME_LIMIT)
        self.assertLess(settings.CELERY_TASK_SOFT_TIME_LIMIT, settings.CELERY_TASK_TIME_LIMIT)


@override_settings(API_INTERNAL_URL="http://api:8000", WORKER_TOKEN="worker-test-token")
class SoftTimeLimitTaskTests(SimpleTestCase):
    def test_soft_time_limit_reports_failure(self):
        calls = []

        def fake_api(method, path, payload=None):
            calls.append((path, payload))
            if path.endswith("/claim/"):
                return {"terminal": False, "target": {"address": "192.0.2.60", "type": "ip"}, "modules": []}
            return {}

        with (
            patch("apps.scans.tasks._api_request", side_effect=fake_api),
            patch("apps.scans.tasks.execute_scan", side_effect=SoftTimeLimitExceeded()),
        ):
            result = execute_batch.run(9, "delivery-9")

        self.assertEqual(result, {"status": "failed"})
        self.assertTrue(calls[-1][0].endswith("/fail/"))
        self.assertIn("time limit", calls[-1][1]["error"])
