from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User, UserGroup
from accounts.models.choices import UserType
from accounts.services.legacy_import_service import LegacyImportService


class LoginImportPolicyTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.payload = {
            "authenticated": True,
            "legacy_user": {
                "username": "access_user",
                "full_name": "Access User",
                "email": "access_user@example.test",
            },
            "groups": [{"name": "ACCESS_GROUP"}],
        }

    @patch("accounts.views.auth.LegacyAuthClient.authenticate")
    def test_unknown_user_imports_access_group_on_first_login(self, bridge_auth):
        bridge_auth.return_value = self.payload
        response = self.client.post(
            "/api/auth/login/", {"username": "access_user", "password": "safe-test-password"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(username="access_user")
        self.assertEqual(user.group.name, "ACCESS_GROUP")
        self.assertEqual(user.legacy_group_name, "ACCESS_GROUP")
        self.assertEqual(response.data["usuario"]["grupo"], "ACCESS_GROUP")
        bridge_auth.assert_called_once()

    @patch("accounts.views.auth.LegacyAuthClient.authenticate")
    def test_existing_user_never_calls_bridge_or_changes_group(self, bridge_auth):
        original = UserGroup.objects.create(user_type=UserType.EMPLOYEE, name="HUB_GROUP")
        user = User.objects.create_user(
            username="access_user", name="Access User", email="access_user@example.test",
            password="safe-test-password", user_origin=User.LEGACY_ORIGIN,
            is_migrated_from_access=True, group=original, legacy_group_name="ACCESS_GROUP"
        )
        response = self.client.post(
            "/api/auth/login/", {"username": "access_user", "password": "safe-test-password"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.group_id, original.id)
        self.assertEqual(response.data["usuario"]["grupo"], "HUB_GROUP")
        bridge_auth.assert_not_called()

    @patch("accounts.views.auth.LegacyAuthClient.authenticate")
    def test_invalid_password_for_existing_user_does_not_fallback(self, bridge_auth):
        User.objects.create_user(
            username="access_user", name="Access User", email="access_user@example.test",
            password="correct-password"
        )
        response = self.client.post(
            "/api/auth/login/", {"username": "access_user", "password": "wrong-password"}, format="json"
        )
        self.assertEqual(response.status_code, 401)
        bridge_auth.assert_not_called()

    def test_reimport_does_not_override_existing_user(self):
        hub = UserGroup.objects.create(user_type=UserType.EMPLOYEE, name="HUB_GROUP")
        user = User.objects.create_user(
            username="access_user", name="Hub User", email="hub_user@example.test",
            password="hub-password", group=hub
        )
        returned = LegacyImportService().import_user_from_legacy_payload(
            self.payload, "access-password"
        )
        user.refresh_from_db()
        self.assertEqual(returned.pk, user.pk)
        self.assertEqual(user.group_id, hub.pk)
        self.assertEqual(user.name, "Hub User")
        self.assertTrue(user.check_password("hub-password"))
