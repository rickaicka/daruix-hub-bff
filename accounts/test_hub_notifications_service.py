from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from accounts.services.notifications import publish, resolve
from accounts.models import HubNotification

class NotificationServiceTests(TestCase):
    def setUp(self):
        # Alguns projetos possuem um modelo de usuário customizado com campos extras.
        self.assertTrue(callable(publish))

    def test_publish_rejects_missing_resource(self):
        with self.assertRaises(ValueError):
            publish(module='obras', event='rm.submitted', recipients=[], title='Teste',
                    resource_type='material_requisition', resource_id='')

    def test_resolve_requires_scope(self):
        with self.assertRaises(ValueError):
            resolve(module='obras')
