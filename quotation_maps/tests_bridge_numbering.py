from unittest.mock import patch
from django.test import SimpleTestCase, override_settings
from quotation_maps.order_numbering import legacy_last_sequence

class BridgeOrderNumberingTests(SimpleTestCase):
    @override_settings(OC_LEGACY_LAST_BY_PC={})
    @patch('integrations.legacy_bridge.client.LegacyBridgeClient.last_purchase_order_sequence')
    @patch('integrations.legacy_bridge.client.LegacyBridgeClient.__init__', return_value=None)
    def test_bridge_sequence(self, init, lookup):
        lookup.return_value = {'pc':'PC26105', 'found': True, 'last_suffix': 4, 'matched_orders': 2, 'source': 'tblOrdemDeCompra'}
        self.assertEqual(legacy_last_sequence('PC26105'), 4)

    @override_settings(OC_LEGACY_LAST_BY_PC={})
    @patch('integrations.legacy_bridge.client.LegacyBridgeClient.last_purchase_order_sequence')
    @patch('integrations.legacy_bridge.client.LegacyBridgeClient.__init__', return_value=None)
    def test_invalid_response_blocks(self, init, lookup):
        lookup.return_value = {'pc':'PC26105', 'found': False, 'last_suffix': 0, 'matched_orders': 3, 'source': 'tblOrdemDeCompra'}
        with self.assertRaises(ValueError):
            legacy_last_sequence('PC26105')
