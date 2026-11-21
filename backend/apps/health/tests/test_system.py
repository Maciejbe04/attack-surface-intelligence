from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import UserProfile


class SystemInfoAPITests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="sys-user", password="test-password")
        UserProfile.objects.create(user=self.user, role=UserProfile.Role.VIEWER)
        self.client = APIClient()

    def test_requires_authentication(self) -> None:
        response = self.client.get(reverse("system-info"))
        self.assertIn(response.status_code, {401, 403})

    @override_settings(
        DEFECTDOJO_URL="http://defectdojo:8080",
        DEFECTDOJO_PASSWORD="secret",
        DEFECTDOJO_VERSION="3.5.202",
        APP_VERSION="0.1.0",
        HTTPX_VERSION="v1.6.9",
    )
    def test_authenticated_user_gets_stack_and_integrations(self) -> None:
        self.client.force_login(self.user)
        response = self.client.get(reverse("system-info"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["app"]["version"], "0.1.0")
        self.assertTrue(payload["integrations"])
        defectdojo = payload["integrations"][0]
        self.assertEqual(defectdojo["id"], "defectdojo")
        self.assertTrue(defectdojo["enabled"])
        self.assertEqual(defectdojo["status"], "configured")
        self.assertEqual(defectdojo["version"], "3.5.202")
        component_ids = {item["id"] for item in payload["stack"]}
        self.assertIn("postgresql", component_ids)
        self.assertIn("redis", component_ids)
        self.assertIn("defectdojo", component_ids)
