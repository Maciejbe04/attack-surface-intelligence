import pyotp
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings

from apps.mfa import services
from apps.mfa.admin_guard import SESSION_MFA_VERIFIED_AT


class AdminMfaGuardTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_superuser("root", password="x" * 20)

    def request(self, verified: bool):
        request = RequestFactory().get("/admin/")
        request.user = self.user
        request.session = {SESSION_MFA_VERIFIED_AT: 1} if verified else {}
        return request

    def enroll(self):
        enrollment = services.start_enrollment(self.user)
        services.confirm_enrollment(self.user, pyotp.TOTP(enrollment.secret).now())

    def test_admin_without_mfa_unaffected(self):
        self.assertTrue(admin.site.has_permission(self.request(verified=False)))

    def test_admin_with_mfa_requires_second_factor_session(self):
        self.enroll()
        self.assertFalse(admin.site.has_permission(self.request(verified=False)))
        self.assertTrue(admin.site.has_permission(self.request(verified=True)))

    @override_settings(MFA_ENABLED=False)
    def test_guard_dormant_when_feature_off(self):
        self.enroll()
        self.assertTrue(admin.site.has_permission(self.request(verified=False)))
