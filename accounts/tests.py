from django.test import TestCase

# Create your tests here.

from unittest.mock import patch
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from accounts.admin import UserAdmin
from accounts.models import User


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
