from io import StringIO

from django.contrib.auth import authenticate, get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts import throttle
from apps.accounts.mfa import MFA_PENDING_MAX_ATTEMPTS, issue_pending_mfa
from apps.accounts.models import UserProfile

PASSWORD = "Str0ng-and-l0ng-passphrase"
LOGIN = "/api/auth/login/"


class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user("alice", password=PASSWORD)
        self.client = APIClient()

    def login(self, password, ip="198.51.100.7", username="alice"):
        return self.client.post(
            LOGIN, {"username": username, "password": password}, format="json", HTTP_X_REAL_IP=ip
        )

    def test_lockout_after_failures_even_with_correct_password(self):
        for _ in range(throttle.MAX_FAILURES_PER_USER_AND_IP):
            self.assertEqual(self.login("wrong").status_code, 401)
        response = self.login(PASSWORD)
        self.assertEqual(response.status_code, 429)
        self.assertNotIn("sessionid", response.cookies)

    def test_other_ip_not_blocked_by_single_ip_lockout(self):
        for _ in range(throttle.MAX_FAILURES_PER_USER_AND_IP):
            self.login("wrong", ip="198.51.100.7")
        self.assertEqual(self.login(PASSWORD, ip="203.0.113.9").status_code, 200)

    def test_account_locked_when_attack_is_spread_over_ips(self):
        for index in range(throttle.MAX_FAILURES_PER_USER):
            self.login("wrong", ip=f"203.0.113.{index + 1}")
        self.assertEqual(self.login(PASSWORD, ip="192.0.2.200").status_code, 429)

    def test_success_resets_account_counters(self):
        for _ in range(throttle.MAX_FAILURES_PER_USER_AND_IP - 1):
            self.login("wrong")
        self.assertEqual(self.login(PASSWORD).status_code, 200)
        self.client.logout()
        for _ in range(throttle.MAX_FAILURES_PER_USER_AND_IP - 1):
            self.login("wrong")
        self.assertEqual(self.login(PASSWORD).status_code, 200)

    def test_password_spraying_from_one_ip_is_blocked(self):
        for index in range(throttle.MAX_FAILURES_PER_IP):
            self.login("wrong", username=f"user{index}")
        self.assertEqual(self.login(PASSWORD).status_code, 429)

    def test_admin_login_path_is_throttled_too(self):
        request = RequestFactory().post("/admin/login/", REMOTE_ADDR="192.0.2.10")
        for _ in range(throttle.MAX_FAILURES_PER_USER_AND_IP):
            self.assertIsNone(authenticate(request, username="alice", password="wrong"))
        self.assertIsNone(authenticate(request, username="alice", password=PASSWORD))

    def test_cache_keys_do_not_contain_username_or_ip(self):
        keys = throttle._keys("alice", "198.51.100.7")
        for key, _ in keys.values():
            self.assertNotIn("alice", key)
            self.assertNotIn("198.51.100.7", key)

    @override_settings(TRUST_X_REAL_IP=False)
    def test_untrusted_header_ignored(self):
        request = RequestFactory().get("/", REMOTE_ADDR="10.0.0.5", HTTP_X_REAL_IP="1.2.3.4")
        self.assertEqual(throttle.client_ip(request), "10.0.0.5")

    def test_garbage_ip_header_falls_back(self):
        request = RequestFactory().get("/", REMOTE_ADDR="10.0.0.5", HTTP_X_REAL_IP="not-an-ip")
        self.assertEqual(throttle.client_ip(request), "10.0.0.5")


class LegacyMfaVerifyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user("bob", password=PASSWORD)
        UserProfile.objects.create(user=self.user, mfa_enabled=True, mfa_secret="JBSWY3DPEHPK3PXP")
        self.client = APIClient()

    def test_wrong_code_does_not_mint_new_tokens_and_attempts_are_limited(self):
        token = issue_pending_mfa(self.user.id, self.user.username)
        for attempt in range(MFA_PENDING_MAX_ATTEMPTS):
            response = self.client.post(
                "/api/auth/mfa/verify/", {"mfa_token": token, "code": "000000"}, format="json"
            )
            self.assertEqual(response.status_code, 401)
            if attempt < MFA_PENDING_MAX_ATTEMPTS - 1:
                self.assertEqual(response.data["mfa_token"], token)
            else:
                self.assertNotIn("mfa_token", response.data)
        response = self.client.post(
            "/api/auth/mfa/verify/", {"mfa_token": token, "code": "000000"}, format="json"
        )
        self.assertIn("expired", response.data["detail"])

    def test_token_not_stored_in_cache_key(self):
        token = issue_pending_mfa(self.user.id, self.user.username)
        self.assertIsNone(cache.get(f"mfa_pending:{token}"))


class BootstrapAdminTests(TestCase):
    def test_legacy_enable_mfa_refused_and_creates_nothing(self):
        with self.assertRaises(CommandError):
            call_command("bootstrap_admin", "--username", "root", "--enable-mfa")
        self.assertFalse(get_user_model().objects.filter(username="root").exists())

    @override_settings(DEBUG=False)
    def test_default_password_warns(self):
        err = StringIO()
        call_command("bootstrap_admin", "--username", "admin", stdout=StringIO(), stderr=err)
        self.assertIn("SECURITY WARNING", err.getvalue())

    @override_settings(DEBUG=False)
    def test_strong_password_no_warning(self):
        err = StringIO()
        call_command(
            "bootstrap_admin", "--username", "admin2", "--password", PASSWORD, stdout=StringIO(), stderr=err
        )
        self.assertNotIn("SECURITY WARNING", err.getvalue())
