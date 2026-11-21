from datetime import timedelta
from unittest import mock

import pyotp
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.mfa import services
from apps.mfa.models import MfaCredential, MfaRecoveryCode

T0 = 1_800_000_000.0


def at(timestamp):
    return mock.patch("apps.mfa.totp._now", return_value=timestamp)


class MfaServiceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user("alice", password="correct horse battery")

    def enroll(self):
        enrollment = services.start_enrollment(self.user)
        otp = pyotp.TOTP(enrollment.secret)
        with at(T0):
            codes = services.confirm_enrollment(self.user, otp.at(T0))
        return enrollment, otp, codes

    # ----------------------------------------------------------- storage

    def test_secret_never_stored_in_plaintext(self):
        enrollment = services.start_enrollment(self.user)
        credential = MfaCredential.objects.get(user=self.user)
        stored = bytes(credential.secret_encrypted)
        self.assertNotIn(enrollment.secret.encode(), stored)
        with connection.cursor() as cursor:
            cursor.execute("SELECT secret_encrypted FROM mfa_mfacredential")
            raw = bytes(cursor.fetchone()[0])
        self.assertNotIn(enrollment.secret.encode(), raw)
        self.assertNotIn(enrollment.secret, repr(credential))

    def test_recovery_codes_stored_only_as_digests(self):
        _, _, codes = self.enroll()
        self.assertEqual(len(codes), services.RECOVERY_CODE_COUNT)
        self.assertEqual(len(set(codes)), len(codes))
        stored = list(MfaRecoveryCode.objects.values_list("code_digest", flat=True))
        for code in codes:
            plain = code.replace("-", "")
            self.assertFalse(any(plain in digest or code in digest for digest in stored))
        self.assertTrue(all(len(digest) == 64 for digest in stored))

    # ----------------------------------------------------------- enrollment

    def test_enrollment_requires_valid_code(self):
        services.start_enrollment(self.user)
        with self.assertRaises(services.InvalidCode):
            services.confirm_enrollment(self.user, "000000")
        self.assertFalse(services.user_has_mfa(self.user))

    def test_enrollment_activates_mfa(self):
        self.enroll()
        self.assertTrue(services.user_has_mfa(self.user))
        self.assertTrue(services.login_requires_mfa(self.user))

    def test_cannot_enroll_twice(self):
        self.enroll()
        with self.assertRaises(services.AlreadyEnrolled):
            services.start_enrollment(self.user)

    def test_enrollment_expires(self):
        enrollment = services.start_enrollment(self.user)
        MfaCredential.objects.filter(user=self.user).update(
            enrollment_started_at=timezone.now() - services.ENROLLMENT_TTL - timedelta(seconds=1)
        )
        with self.assertRaises(services.EnrollmentExpired):
            services.confirm_enrollment(self.user, pyotp.TOTP(enrollment.secret).now())
        self.assertFalse(services.user_has_mfa(self.user))

    def test_restarting_enrollment_replaces_secret(self):
        first = services.start_enrollment(self.user)
        second = services.start_enrollment(self.user)
        self.assertNotEqual(first.secret, second.secret)
        with at(T0), self.assertRaises(services.InvalidCode):
            services.confirm_enrollment(self.user, pyotp.TOTP(first.secret).at(T0))

    @override_settings(MFA_ENABLED=False)
    def test_feature_flag_off_means_no_mfa_at_login(self):
        self.enroll()
        self.assertFalse(services.login_requires_mfa(self.user))

    # ----------------------------------------------------------- verification

    def test_totp_replay_rejected(self):
        _, otp, _ = self.enroll()
        # The enrollment code itself cannot be replayed.
        with at(T0), self.assertRaises(services.InvalidCode):
            services.verify_second_factor(self.user, otp.at(T0))
        with at(T0 + 30):
            self.assertEqual(services.verify_second_factor(self.user, otp.at(T0 + 30)), "totp")
        with at(T0 + 30), self.assertRaises(services.InvalidCode):
            services.verify_second_factor(self.user, otp.at(T0 + 30))

    def test_older_step_rejected_after_newer_used(self):
        _, otp, _ = self.enroll()
        with at(T0 + 60):
            services.verify_second_factor(self.user, otp.at(T0 + 60))
        with at(T0 + 60), self.assertRaises(services.InvalidCode):
            services.verify_second_factor(self.user, otp.at(T0 + 30))

    def test_recovery_code_single_use(self):
        _, _, codes = self.enroll()
        self.assertEqual(services.verify_second_factor(self.user, codes[0].lower()), "recovery_code")
        self.assertEqual(services.remaining_recovery_codes(self.user), services.RECOVERY_CODE_COUNT - 1)
        with self.assertRaises(services.InvalidCode):
            services.verify_second_factor(self.user, codes[0])

    def test_recovery_code_of_other_user_rejected(self):
        _, _, codes = self.enroll()
        bob = get_user_model().objects.create_user("bob", password="x")
        enrollment = services.start_enrollment(bob)
        with at(T0):
            services.confirm_enrollment(bob, pyotp.TOTP(enrollment.secret).at(T0))
        with self.assertRaises(services.InvalidCode):
            services.verify_second_factor(bob, codes[1])

    def test_lockout_after_repeated_failures(self):
        _, otp, codes = self.enroll()
        for _ in range(services.MAX_FAILED_ATTEMPTS):
            with self.assertRaises(services.InvalidCode):
                services.verify_second_factor(self.user, "ZZZZZ-ZZZZZ")
        with at(T0 + 30), self.assertRaises(services.LockedOut):
            services.verify_second_factor(self.user, otp.at(T0 + 30))
        with self.assertRaises(services.LockedOut):
            services.verify_second_factor(self.user, codes[0])

    def test_success_resets_failure_counter(self):
        _, otp, _ = self.enroll()
        for _ in range(services.MAX_FAILED_ATTEMPTS - 1):
            with self.assertRaises(services.InvalidCode):
                services.verify_second_factor(self.user, "000000")
        with at(T0 + 30):
            services.verify_second_factor(self.user, otp.at(T0 + 30))
        self.assertFalse(services.is_locked_out(self.user))

    def test_not_enrolled(self):
        with self.assertRaises(services.NotEnrolled):
            services.verify_second_factor(self.user, "123456")

    # ----------------------------------------------------------- management

    def test_regenerate_requires_totp_not_recovery_code(self):
        _, otp, codes = self.enroll()
        with self.assertRaises(services.InvalidCode):
            services.regenerate_recovery_codes(self.user, codes[0])
        with at(T0 + 30):
            new_codes = services.regenerate_recovery_codes(self.user, otp.at(T0 + 30))
        self.assertTrue(set(new_codes).isdisjoint(codes))
        with self.assertRaises(services.InvalidCode):
            services.verify_second_factor(self.user, codes[1])

    def test_disable(self):
        _, otp, _ = self.enroll()
        with at(T0 + 30):
            services.disable(self.user, otp.at(T0 + 30))
        self.assertFalse(services.user_has_mfa(self.user))
        self.assertFalse(MfaRecoveryCode.objects.exists())

    def test_admin_reset(self):
        self.enroll()
        self.assertTrue(services.admin_reset(self.user))
        self.assertFalse(services.user_has_mfa(self.user))

    def test_rotate_encryption(self):
        enrollment, otp, _ = self.enroll()
        new_key = "rotated-master-key-for-tests-0123456789abcdef"
        from django.conf import settings

        with override_settings(APP_DATA_KEY=new_key, APP_DATA_KEY_PREVIOUS=settings.APP_DATA_KEY):
            self.assertEqual(services.rotate_encryption(), 1)
            self.assertEqual(services.rotate_encryption(), 0)
        with override_settings(APP_DATA_KEY=new_key, APP_DATA_KEY_PREVIOUS=""):
            with at(T0 + 30):
                self.assertEqual(services.verify_second_factor(self.user, otp.at(T0 + 30)), "totp")
