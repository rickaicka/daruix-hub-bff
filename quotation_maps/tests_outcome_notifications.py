from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from .outcome_notifications import prepare_outcome_notifications


class RecipientSelectionTests(SimpleTestCase):
    @patch("quotation_maps.outcome_notifications.TenderOutcomeNotification.objects.get_or_create")
    @patch("quotation_maps.outcome_notifications.TenderBid.objects.filter")
    @patch("quotation_maps.outcome_notifications.PurchaseOrder.objects.filter")
    def test_only_submitted_non_awarded_suppliers_receive_messages(self, order_filter, bid_filter, notice_create):
        quotation = MagicMock(pk=3)
        order_filter.return_value.values_list.return_value = [1]
        awarded = MagicMock(supplier_id=1)
        awarded.supplier.email = "winner@example.test"
        other = MagicMock(supplier_id=2)
        other.supplier.email = "other@example.test"
        bid_filter.return_value.exclude.return_value.select_related.return_value = [awarded, other]
        notice = MagicMock(pk=17)
        notice_create.return_value = (notice, True)
        self.assertEqual(prepare_outcome_notifications(quotation), [17])
        self.assertEqual(notice_create.call_count, 1)
        self.assertEqual(notice_create.call_args.kwargs["supplier"], other.supplier)
