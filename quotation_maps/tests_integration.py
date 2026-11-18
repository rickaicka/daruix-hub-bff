from django.test import SimpleTestCase
from django.test import override_settings
from rest_framework.test import APIRequestFactory
from unittest.mock import patch
from .order_numbering import make_order_code, legacy_last_sequence
from .integration_api import hub_purchase_orders

class OrderNumberingTests(SimpleTestCase):
    def test_code_from_pc(self):
        self.assertEqual(make_order_code('PC26031', 1), 'OC26031001')
        self.assertEqual(make_order_code('PC21065', 240), 'OC21065240')
        self.assertEqual(make_order_code('PC26031', 999), 'OC26031999')

    def test_invalid_pc_or_sequence(self):
        for pc, seq in [('26031', 1), ('PC2603', 1), ('PC26031', 0), ('PC26031', 1000)]:
            with self.subTest(pc=pc, seq=seq), self.assertRaises(ValueError):
                make_order_code(pc, seq)

    @override_settings(OC_LEGACY_LAST_BY_PC={'PC26031': 2})
    def test_legacy_baseline(self):
        self.assertEqual(legacy_last_sequence('PC26031'), 2)
        with self.assertRaises(ValueError):
            legacy_last_sequence('PC25017')

class IntegrationSecurityTests(SimpleTestCase):
    @override_settings(HUB_ORDERS_INTEGRATION_KEY='test-local-secret')
    def test_denies_missing_key(self):
        request = APIRequestFactory().get('/api/quotation-maps/integration/purchase-orders/')
        response = hub_purchase_orders(request)
        self.assertEqual(response.status_code, 403)

    @override_settings(HUB_ORDERS_INTEGRATION_KEY='')
    def test_disabled_by_default(self):
        request = APIRequestFactory().get('/api/quotation-maps/integration/purchase-orders/')
        response = hub_purchase_orders(request)
        self.assertEqual(response.status_code, 503)
