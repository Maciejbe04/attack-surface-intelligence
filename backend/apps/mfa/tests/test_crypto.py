from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from apps.mfa import crypto

KEY_A = "a" * 20 + "first-master-key-for-tests-xyz"
KEY_B = "b" * 20 + "second-master-key-for-tests-xy"


@override_settings(APP_DATA_KEY=KEY_A, APP_DATA_KEY_PREVIOUS="")
class CryptoTests(SimpleTestCase):
    def test_round_trip(self):
        blob = crypto.encrypt(b"JBSWY3DPEHPK3PXP", purpose="p", aad=b"user:1")
        self.assertEqual(crypto.decrypt(blob, purpose="p", aad=b"user:1"), b"JBSWY3DPEHPK3PXP")

    def test_ciphertext_hides_plaintext_and_is_randomized(self):
        first = crypto.encrypt(b"JBSWY3DPEHPK3PXP", purpose="p", aad=b"user:1")
        second = crypto.encrypt(b"JBSWY3DPEHPK3PXP", purpose="p", aad=b"user:1")
        self.assertNotIn(b"JBSWY3DPEHPK3PXP", first)
        self.assertNotEqual(first, second)

    def test_blob_bound_to_owner(self):
        blob = crypto.encrypt(b"secret", purpose="p", aad=b"user:1")
        with self.assertRaises(crypto.DecryptionError):
            crypto.decrypt(blob, purpose="p", aad=b"user:2")

    def test_blob_bound_to_purpose(self):
        blob = crypto.encrypt(b"secret", purpose="p", aad=b"user:1")
        with self.assertRaises(crypto.DecryptionError):
            crypto.decrypt(blob, purpose="other", aad=b"user:1")

    def test_tampering_detected(self):
        blob = bytearray(crypto.encrypt(b"secret", purpose="p", aad=b"user:1"))
        blob[-1] ^= 0x01
        with self.assertRaises(crypto.DecryptionError):
            crypto.decrypt(bytes(blob), purpose="p", aad=b"user:1")

    def test_truncated_blob_rejected(self):
        with self.assertRaises(crypto.DecryptionError):
            crypto.decrypt(b"\x01abc", purpose="p", aad=b"user:1")

    @override_settings(APP_DATA_KEY="")
    def test_missing_key_fails_closed(self):
        with self.assertRaises(ImproperlyConfigured):
            crypto.encrypt(b"secret", purpose="p", aad=b"user:1")

    @override_settings(APP_DATA_KEY="too-short")
    def test_short_key_fails_closed(self):
        with self.assertRaises(ImproperlyConfigured):
            crypto.encrypt(b"secret", purpose="p", aad=b"user:1")

    def test_key_rotation(self):
        blob = crypto.encrypt(b"secret", purpose="p", aad=b"user:1")
        with override_settings(APP_DATA_KEY=KEY_B, APP_DATA_KEY_PREVIOUS=KEY_A):
            self.assertEqual(crypto.decrypt(blob, purpose="p", aad=b"user:1"), b"secret")
            self.assertTrue(crypto.needs_rotation(blob, purpose="p"))
            fresh = crypto.encrypt(b"secret", purpose="p", aad=b"user:1")
            self.assertFalse(crypto.needs_rotation(fresh, purpose="p"))
        with override_settings(APP_DATA_KEY=KEY_B, APP_DATA_KEY_PREVIOUS=""):
            with self.assertRaises(crypto.DecryptionError):
                crypto.decrypt(blob, purpose="p", aad=b"user:1")

    def test_keyed_digest_depends_on_key(self):
        digest_a = crypto.keyed_digest(b"value", purpose="p")
        with override_settings(APP_DATA_KEY=KEY_B, APP_DATA_KEY_PREVIOUS=KEY_A):
            digests = crypto.keyed_digests(b"value", purpose="p")
        self.assertNotEqual(digests[0], digest_a)
        self.assertEqual(digests[1], digest_a)
        self.assertNotIn("value", digest_a)
