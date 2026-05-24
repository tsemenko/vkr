from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import WebGroupRole, WebUserPasswordState
from accounts.services.monitoring import empty_snapshot, get_or_build_snapshot


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
        for url_name in ["index", "ad_analytics", "create_account", "logs", "error_logs", "system_management", "system_logs"]:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)

    @patch("accounts.views._analytics_context")
    def test_fragment_endpoint_returns_json(self, analytics_context):
        analytics_context.return_value = empty_snapshot()
        self.client.force_login(self.user)
        response = self.client.get(reverse("ad_analytics_fragment"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ok"], True)
        self.assertIn("html", response.json())

    def test_change_web_user_role_requires_users_section_access(self):
        branch_manager = get_user_model().objects.create_user(username="branch_manager")
        target_user = get_user_model().objects.create_user(username="target_user")
        branch_group = Group.objects.create(name="Branch Managers")
        users_group = Group.objects.create(name="User Managers")
        new_role_group = Group.objects.create(name="New User Role")

        WebGroupRole.objects.create(group=branch_group, allowed_sections=["branches"])
        WebGroupRole.objects.create(group=users_group, allowed_sections=["users"])
        new_role = WebGroupRole.objects.create(group=new_role_group, allowed_sections=["monitoring"])
        branch_manager.groups.add(branch_group)

        self.client.force_login(branch_manager)
        response = self.client.post(
            reverse("system_management"),
            {
                "action": "change_web_user_role",
                "section": "branches",
                "user_id": target_user.pk,
                "role_id": new_role.pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{reverse('system_management')}?section=branches")
        self.assertFalse(target_user.groups.filter(pk=new_role_group.pk).exists())

    @patch("accounts.services.monitoring.cache.get")
    def test_monitoring_falls_back_when_cache_is_unavailable(self, cache_get):
        cache_get.side_effect = RuntimeError("cache unavailable")

        snapshot = get_or_build_snapshot()

        self.assertEqual(snapshot["monitoring_status"], "warming_up")

    def test_user_with_temporary_password_must_change_it_after_login(self):
        user = get_user_model().objects.create_user(username="temp_user", password="TempPass123!")
        WebUserPasswordState.objects.create(user=user, must_change_password=True)

        self.assertTrue(self.client.login(username="temp_user", password="TempPass123!"))
        response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("change_initial_password"))

        response = self.client.post(
            reverse("change_initial_password"),
            {
                "old_password": "TempPass123!",
                "new_password1": "PermanentPass123!",
                "new_password2": "PermanentPass123!",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("index"))
        user.refresh_from_db()
        self.assertTrue(user.check_password("PermanentPass123!"))
        self.assertFalse(user.password_state.must_change_password)
