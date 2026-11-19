from datetime import date
from django.test import SimpleTestCase, override_settings
from .delivery_deadlines import parse_delivery_terms, expected_delivery_date


class DeliveryDeadlineTests(SimpleTestCase):
    def test_parses_new_fields(self):
        self.assertEqual(parse_delivery_terms("10 dias úteis"), (10, "BUSINESS"))
        self.assertEqual(parse_delivery_terms("5 dias corridos"), (5, "CALENDAR"))
        self.assertIsNone(parse_delivery_terms("a combinar"))

    def test_business_excludes_weekend(self):
        self.assertEqual(expected_delivery_date(date(2026, 11, 19), 2, "BUSINESS"), date(2026, 11, 23))

    def test_national_holiday(self):
        # 20/11/2026 é feriado nacional e 21-22/11 é fim de semana.
        self.assertEqual(expected_delivery_date(date(2026, 11, 19), 1, "BUSINESS"), date(2026, 11, 23))

    def test_calendar_counts_weekend_and_holiday(self):
        self.assertEqual(expected_delivery_date(date(2026, 11, 19), 2, "CALENDAR"), date(2026, 11, 21))

    @override_settings(QUOTATION_DELIVERY_EXTRA_HOLIDAYS=["2026-11-23"])
    def test_local_configured_holiday(self):
        self.assertEqual(expected_delivery_date(date(2026, 11, 19), 1, "BUSINESS"), date(2026, 11, 24))

    def test_easter_good_friday(self):
        self.assertEqual(expected_delivery_date(date(2026, 4, 2), 1, "BUSINESS"), date(2026, 4, 6))
