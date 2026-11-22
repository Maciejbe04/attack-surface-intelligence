from django.test import SimpleTestCase, override_settings
from unittest.mock import patch

from apps.scans.modules import validate_modules
from apps.scans.runner import _httpx_arguments, _module_map, _nmap_arguments


def val(arguments, flag):
    return arguments[arguments.index(flag) + 1]


class IntensityCapTests(SimpleTestCase):
    def nmap(self, **port_filters):
        modules = validate_modules([
            {"id": "port-scan", "filters": {"profile": "custom", "customPorts": "80", **port_filters}},
            {"id": "service-detect", "filters": {"intensity": 9}},
        ])
        with patch("apps.scans.runner._supports_syn_scan", return_value=False):
            args, _ = _nmap_arguments("192.0.2.1", "ip", _module_map(modules))
        return args

    def test_nmap_rate_capped(self):
        args = self.nmap(maxRate=5000, timing="T4")
        self.assertEqual(val(args, "--max-rate"), "1000")      # capped from 5000
        self.assertIn("-T3", args)                              # T4 downgraded
        self.assertNotIn("-T4", args)
        self.assertEqual(val(args, "--version-intensity"), "7")  # capped from 9

    def test_lower_values_kept(self):
        args = self.nmap(maxRate=120, timing="T2")
        self.assertEqual(val(args, "--max-rate"), "120")
        self.assertIn("-T2", args)

    @override_settings(SCAN_ALLOW_AGGRESSIVE_TIMING=True, SCAN_MAX_RATE_CEILING=6000)
    def test_ceilings_configurable(self):
        args = self.nmap(maxRate=5000, timing="T4")
        self.assertEqual(val(args, "--max-rate"), "5000")
        self.assertIn("-T4", args)

    def test_httpx_rate_and_threads_capped(self):
        modules = validate_modules([{"id": "http-fingerprint", "filters": {"rateLimit": 500}}])
        args = _httpx_arguments(_module_map(modules))
        self.assertEqual(val(args, "-rate-limit"), "150")
        self.assertEqual(val(args, "-threads"), "50")
