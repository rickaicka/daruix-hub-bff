from django.test import TestCase

# Create your tests here.

from unittest.mock import patch
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from accounts.admin import UserAdmin
from accounts.models import User


class LegacyGroupResyncTests(TestCase):
    def test_existing_account_gets_group_without_recreating_user(self):
        user = User.objects.create_user(username="legacy_old", name="Legacy", email="legacy_old@example.test", password="pass123", user_origin=User.LEGACY_ORIGIN)
        pk = user.pk
        changed = LegacyImportService().synchronize_existing_user_group(user, {"groups": [{"name": "COLABORADOR | COMPRAS"}]})
        user.refresh_from_db()
        self.assertTrue(changed)
        self.assertEqual(user.pk, pk)
        self.assertEqual(user.group.name, "COLABORADOR | COMPRAS")

    def test_missing_group_does_not_erase_existing_group(self):
        group = UserGroup.objects.create(user_type=UserType.EMPLOYEE, name="COMPRAS")
        user = User.objects.create_user(username="legacy_stable", name="Legacy", email="legacy_stable@example.test", password="pass123", user_origin=User.LEGACY_ORIGIN, group=group)
        self.assertFalse(LegacyImportService().synchronize_existing_user_group(user, {"groups": []}))
        user.refresh_from_db()
        self.assertEqual(user.group_id, group.pk)

    def test_django_user_cannot_be_given_legacy_group(self):
        user = User.objects.create_user(username="native", name="Native", email="native@example.test", password="pass123")
        self.assertFalse(LegacyImportService().synchronize_existing_user_group(user, {"groups": [{"name": "DIRETORIA"}]}))
        user.refresh_from_db()
        self.assertIsNone(user.group)


class SafeUserAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(username="rootadmin", email="rootadmin@example.test", name="Admin", password="pass123")
        self.target = User.objects.create_user(username="test_unlinked", email="test_unlinked@example.test", name="Target", password="pass123")
        self.admin = UserAdmin(User, AdminSite())
        self.request = RequestFactory().post("/admin/accounts/user/")
        self.request.user = self.admin_user

    @patch.object(UserAdmin, "message_user")
    def test_safe_delete_unlinked_user(self, _message):
        self.admin.delete_unlinked_users(self.request, User.objects.filter(pk=self.target.pk))
        self.assertFalse(User.objects.filter(pk=self.target.pk).exists())

    @patch.object(UserAdmin, "message_user")
    def test_does_not_delete_superuser(self, _message):
        self.admin.delete_unlinked_users(self.request, User.objects.filter(pk=self.admin_user.pk))
        self.assertTrue(User.objects.filter(pk=self.admin_user.pk).exists())
