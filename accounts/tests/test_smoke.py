from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.services.monitoring import empty_snapshot


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class SmokeTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_superuser(username="admin", email="admin@example.com", password="adminpass123")

    def test_login_page_renders(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Веб-сервис AD")

    @patch("accounts.views._analytics_context")
    def test_main_pages_render_for_authorized_user(self, analytics_context):
        analytics_context.return_value = empty_snapshot()
        self.client.force_login(self.user)
        for url_name in ["index", "ad_analytics", "create_account", "logs", "error_logs", "system_management"]:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)

    @patch("accounts.views._analytics_context")
    def test_fragment_endpoint_returns_json(self, analytics_context):
        analytics_context.return_value = empty_snapshot()
        self.client.force_login(self.user)
        response = self.client.get(reverse("ad_analytics_fragment"), {"refresh": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ok"], True)
        self.assertIn("html", response.json())
