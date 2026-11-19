from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .invitations import close_expired_tender, invite_selected


class TenderLifecycleTests(SimpleTestCase):
    def fake_map(self, *, expired=True):
        m = MagicMock()
        m.tender_opened_at = timezone.now() - timedelta(days=2)
        m.tender_closed_at = None
        m.tender_deadline = timezone.now() - timedelta(minutes=1) if expired else timezone.now() + timedelta(hours=1)
        m.status = "DRAFT"
        m.version = 2
        m.quotes = [{"supplier": {"id": 10, "name": "A"}, "offers": [{"item_id": 7, "unit_price": "10.00", "notes": "", "selected": False}]}]
        bid = MagicMock(supplier_id=10, offer={"supplier": {"id": 10, "name": "A"}, "offers": [{"item_id": 7, "unit_price": "12.00"}]})
        m.tender_bids.filter.return_value.exclude.return_value.order_by.return_value = [bid]
        return m

    def test_close_merges_submitted_quotes_and_increments_version(self):
        m = self.fake_map()
        self.assertTrue(close_expired_tender(m))
        self.assertEqual(m.version, 3)
        self.assertEqual(m.quotes[0]["offers"][0]["unit_price"], "12.00")
        self.assertIsNotNone(m.tender_closed_at)
        m.save.assert_called_once()

    def test_buyer_can_close_before_deadline(self):
        m = self.fake_map(expired=False)
        self.assertTrue(close_expired_tender(m, allow_early=True))
        self.assertIsNotNone(m.tender_closed_at)
        self.assertEqual(m.version, 3)
        m.save.assert_called_once()

    def test_does_not_close_before_deadline(self):
        m = self.fake_map(expired=False)
        self.assertFalse(close_expired_tender(m))
        m.save.assert_not_called()

    def test_close_is_idempotent(self):
        m = self.fake_map()
        self.assertTrue(close_expired_tender(m))
        self.assertFalse(close_expired_tender(m))
        m.save.assert_called_once()

    def test_requires_four_to_six_suppliers(self):
        m = MagicMock()
        m.quotes = [{"supplier": {"id": 1}}]
        with self.assertRaises(ValidationError):
            invite_selected(m)

    def test_rejects_duplicate_supplier(self):
        m = MagicMock()
        m.quotes = [{"supplier": {"id": 1}}] * 4
        with self.assertRaises(ValidationError):
            invite_selected(m)


class QuotationMapSequenceTests(SimpleTestCase):
    def test_first_map_has_three_digit_sequence(self):
        from .services import make_map_code
        self.assertEqual(make_map_code("PC26105", 1), "MC26105-001")

    def test_next_maps_for_same_pc(self):
        from .services import make_map_code
        self.assertEqual(make_map_code("PC26105", 2), "MC26105-002")
        self.assertEqual(make_map_code("PC26105", 12), "MC26105-012")

    def test_invalid_sequence(self):
        from .services import make_map_code
        with self.assertRaises(ValueError):
            make_map_code("PC26105", 0)
