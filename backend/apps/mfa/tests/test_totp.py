import pyotp
from django.test import SimpleTestCase

from apps.mfa import totp

NOW = 1_800_000_000.0


class TotpTests(SimpleTestCase):
    def setUp(self):
        self.secret = totp.generate_secret()
        self.otp = pyotp.TOTP(self.secret)
        self.step = totp.current_step(NOW)

    def test_secret_is_160_bits_base32(self):
        self.assertEqual(len(self.secret), 32)
        self.assertNotEqual(totp.generate_secret(), self.secret)

    def test_current_code_matches_its_step(self):
        self.assertEqual(totp.match_step(self.secret, self.otp.at(NOW), now=NOW), self.step)

    def test_one_step_drift_accepted(self):
        self.assertEqual(totp.match_step(self.secret, self.otp.at(NOW - 30), now=NOW), self.step - 1)
        self.assertEqual(totp.match_step(self.secret, self.otp.at(NOW + 30), now=NOW), self.step + 1)

    def test_old_code_rejected(self):
        self.assertIsNone(totp.match_step(self.secret, self.otp.at(NOW - 90), now=NOW))

    def test_spaces_ignored(self):
        code = self.otp.at(NOW)
        self.assertEqual(totp.match_step(self.secret, f" {code[:3]} {code[3:]} ", now=NOW), self.step)

    def test_garbage_rejected(self):
        for code in ("", None, "12345", "1234567", "abcdef", "12345a"):
            self.assertIsNone(totp.match_step(self.secret, code, now=NOW))

    def test_other_secret_rejected(self):
        other = pyotp.TOTP(totp.generate_secret()).at(NOW)
        if other != self.otp.at(NOW):
            self.assertIsNone(totp.match_step(self.secret, other, now=NOW))
