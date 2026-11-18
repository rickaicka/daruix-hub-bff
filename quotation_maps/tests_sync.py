from copy import deepcopy
from types import SimpleNamespace

from django.test import SimpleTestCase

from .quote_sync import merge_buyer_quotes, merge_supplier_bid


class _Bids:
    def __init__(self, bids):
        self.bids = bids

    def filter(self, **kwargs):
        return self.bids


class QuotationSyncTests(SimpleTestCase):
    def setUp(self):
        self.bid = SimpleNamespace(
            supplier_id=9, submitted_at=None,
            offer=dict(offers=[dict(item_id=1, unit_price="15.00", notes="Nova oferta")],
                       payment="30 dias", delivery="5 dias", quoted_on="2026-11-18",
                       freight="0", discount="0", notes=""),
        )
        self.map = SimpleNamespace(quotes=[dict(
            supplier={"id": 9, "name": "Fornecedor"},
            offers=[dict(item_id=1, unit_price="12.00", selected=True, notes="")],
            payment="", delivery="", quoted_on=None, freight="0", discount="0", notes="",
        )], tender_bids=_Bids([self.bid]))

    def test_first_bid_has_priority_over_previous_manual_value(self):
        self.assertTrue(merge_supplier_bid(self.map, self.bid))
        offer = self.map.quotes[0]["offers"][0]
        self.assertEqual(offer["unit_price"], "15.00")
        self.assertEqual(offer["price_source"], "TENDER")
        self.assertTrue(offer["selected"])
        self.assertEqual(self.map.quotes[0]["payment"], "30 dias")

    def test_manual_override_survives_later_bid_and_can_be_restored(self):
        merge_supplier_bid(self.map, self.bid)
        payload = deepcopy(self.map.quotes)
        payload[0]["offers"][0]["unit_price"] = "17.00"
        self.map.quotes = merge_buyer_quotes(self.map, payload)
        self.bid.offer["offers"][0]["unit_price"] = "16.00"
        merge_supplier_bid(self.map, self.bid)
        offer = self.map.quotes[0]["offers"][0]
        self.assertEqual(offer["unit_price"], "17.00")
        self.assertEqual(offer["tender_unit_price"], "16.00")
        self.assertEqual(offer["price_source"], "ADJUSTED")
        payload = deepcopy(self.map.quotes)
        payload[0]["offers"][0]["restore_tender"] = True
        self.map.quotes = merge_buyer_quotes(self.map, payload)
        self.assertEqual(self.map.quotes[0]["offers"][0]["unit_price"], "16.00")
        self.assertEqual(self.map.quotes[0]["offers"][0]["price_source"], "TENDER")

    def test_manual_without_bid_stays_manual(self):
        self.map.tender_bids = _Bids([])
        result = merge_buyer_quotes(self.map, deepcopy(self.map.quotes))
        self.assertEqual(result[0]["offers"][0]["price_source"], "MANUAL")
