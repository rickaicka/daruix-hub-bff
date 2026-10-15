from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.template.response import TemplateResponse
from django.test import RequestFactory, TestCase

from accounts.admin import UserAdmin
from accounts.models import User


class AdminHardDeleteTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_superuser(
            username='operator', email='operator@example.test', name='Operator', password='pass123'
        )
        self.target = User.objects.create_user(
            username='target', email='target@example.test', name='Target', password='pass123'
        )
        self.admin = UserAdmin(User, AdminSite())
        self.factory = RequestFactory()

    def request(self, confirmation=None, operator=None):
        data = {'action': 'hard_delete_user', '_selected_action': str(self.target.pk)}
        if confirmation is not None:
            data['confirm_hard_delete'] = confirmation
        req = self.factory.post('/admin/accounts/user/', data)
        req.user = operator or self.operator
        return req

    def test_requires_explicit_confirmation(self):
        response = self.admin.hard_delete_user(self.request(), User.objects.filter(pk=self.target.pk))
        self.assertIsInstance(response, TemplateResponse)
        self.assertTrue(User.objects.filter(pk=self.target.pk).exists())

    @patch.object(UserAdmin, 'message_user')
    def test_can_remove_unlinked_user_after_confirmation(self, _messages):
        self.admin.hard_delete_user(
            self.request('EXCLUIR DEFINITIVAMENTE'), User.objects.filter(pk=self.target.pk)
        )
        self.assertFalse(User.objects.filter(pk=self.target.pk).exists())

    @patch.object(UserAdmin, 'message_user')
    def test_cannot_delete_superuser(self, _messages):
        self.admin.hard_delete_user(
            self.request('EXCLUIR DEFINITIVAMENTE'), User.objects.filter(pk=self.operator.pk)
        )
        self.assertTrue(User.objects.filter(pk=self.operator.pk).exists())

    @patch.object(UserAdmin, 'message_user')
    def test_soft_delete_remains_default(self, _messages):
        self.admin.soft_delete_users(self.request(), User.objects.filter(pk=self.target.pk))
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
