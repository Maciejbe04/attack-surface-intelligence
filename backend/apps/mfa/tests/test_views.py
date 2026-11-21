from unittest import mock

import pyotp
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.mfa import challenge, services

T0 = 1_800_000_000.0
PASSWORD = "correct horse battery"
BASE = "/api/auth/mfa/"


def at(timestamp):
    return mock.patch("apps.mfa.totp._now", return_value=timestamp)


@override_settings(ROOT_URLCONF="apps.mfa.tests.urls", MFA_ENABLED=True)
class MfaApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user("alice", password=PASSWORD)
        self.client = APIClient()
        self.client.force_login(self.user)

    def enroll(self):
        response = self.client.post(BASE + "enroll/", {"password": PASSWORD}, format="json")
        self.assertEqual(response.status_code, 201)
        otp = pyotp.TOTP(response.data["secret"])
        with at(T0):
            confirm = self.client.post(BASE + "enroll/confirm/", {"code": otp.at(T0)}, format="json")
        self.assertEqual(confirm.status_code, 200)
        return otp, confirm.data["recovery_codes"]

    def test_requires_authentication(self):
        anonymous = APIClient()
        self.assertIn(anonymous.get(BASE + "status/").status_code, (401, 403))
        self.assertIn(anonymous.post(BASE + "enroll/", {}, format="json").status_code, (401, 403))

    def test_enroll_requires_password(self):
        response = self.client.post(BASE + "enroll/", {"password": "wrong"}, format="json")
        self.assertEqual(response.status_code, 403)
        response = self.client.post(BASE + "enroll/", {}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_secret_responses_not_cached(self):
        response = self.client.post(BASE + "enroll/", {"password": PASSWORD}, format="json")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertTrue(response.data["otpauth_uri"].startswith("otpauth://totp/"))

    def test_full_enrollment_and_status(self):
        _, codes = self.enroll()
        self.assertEqual(len(codes), services.RECOVERY_CODE_COUNT)
        status = self.client.get(BASE + "status/").data
        self.assertTrue(status["enrolled"])
        self.assertEqual(status["recovery_codes_remaining"], services.RECOVERY_CODE_COUNT)
        self.assertNotIn("secret", status)

    def test_login_challenge_creates_session(self):
        otp, _ = self.enroll()
        browser = APIClient()
        token = challenge.issue_challenge(self.user)
        with at(T0 + 30):
            response = browser.post(BASE + "challenge/", {"mfa_token": token, "code": otp.at(T0 + 30)}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["username"], "alice")
        self.assertEqual(browser.get(BASE + "status/").status_code, 200)
        # Token is single use.
        with at(T0 + 60):
            again = browser.post(BASE + "challenge/", {"mfa_token": token, "code": otp.at(T0 + 60)}, format="json")
        self.assertEqual(again.status_code, 401)

    def test_challenge_dies_after_max_attempts(self):
        otp, _ = self.enroll()
        browser = APIClient()
        token = challenge.issue_challenge(self.user)
        for attempt in range(challenge.MAX_ATTEMPTS):
            response = browser.post(BASE + "challenge/", {"mfa_token": token, "code": "000000"}, format="json")
            expected = 401 if attempt == challenge.MAX_ATTEMPTS - 1 else 400
            self.assertEqual(response.status_code, expected)
            self.assertNotIn("mfa_token", response.data)
        with at(T0 + 30):
            response = browser.post(BASE + "challenge/", {"mfa_token": token, "code": otp.at(T0 + 30)}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_unknown_challenge_token(self):
        response = APIClient().post(BASE + "challenge/", {"mfa_token": "nope", "code": "123456"}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_disable_requires_password_and_code(self):
        otp, _ = self.enroll()
        with at(T0 + 30):
            response = self.client.post(BASE + "disable/", {"code": otp.at(T0 + 30)}, format="json")
        self.assertEqual(response.status_code, 403)
        with at(T0 + 30):
            response = self.client.post(
                BASE + "disable/", {"password": PASSWORD, "code": otp.at(T0 + 30)}, format="json"
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(services.user_has_mfa(self.user))

    def test_regenerate_recovery_codes(self):
        otp, codes = self.enroll()
        with at(T0 + 30):
            response = self.client.post(
                BASE + "recovery-codes/", {"password": PASSWORD, "code": otp.at(T0 + 30)}, format="json"
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(set(response.data["recovery_codes"]).isdisjoint(codes))

    def test_wrong_passwords_lead_to_lockout(self):
        for _ in range(services.MAX_FAILED_ATTEMPTS):
            self.client.post(BASE + "enroll/", {"password": "wrong"}, format="json")
        response = self.client.post(BASE + "enroll/", {"password": PASSWORD}, format="json")
        self.assertEqual(response.status_code, 429)

    @override_settings(MFA_ENABLED=False)
    def test_endpoints_hidden_when_feature_disabled(self):
        self.assertEqual(self.client.get(BASE + "status/").status_code, 404)
        self.assertEqual(self.client.post(BASE + "enroll/", {"password": PASSWORD}, format="json").status_code, 404)
        self.assertEqual(APIClient().post(BASE + "challenge/", {}, format="json").status_code, 404)
