from decimal import Decimal, ROUND_HALF_UP
from unittest import TestCase

from django.core.exceptions import ValidationError

from budgeting.services.budget_pricing import discounted_unit_price


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class UnitDiscountTests(TestCase):
    def test_excel_pc25017_rounds_bdi_sale_unit_before_discount(self):
        gross = money(Decimal("10600") * Decimal("1.309712613574"))
        unit = discounted_unit_price(gross, Decimal("3.16"))

        self.assertEqual(gross, Decimal("13882.95"))
        self.assertEqual(unit, Decimal("13879.79"))

    def test_discount_is_per_unit_without_rounding_the_unit_first(self):
        unit = discounted_unit_price(Decimal("10.005"), Decimal("1.00"))

        self.assertEqual(unit, Decimal("9.005"))
        self.assertEqual(money(unit * 3), Decimal("27.02"))

    def test_reference_874188_times_67(self):
        unit = discounted_unit_price(Decimal("87.4188"))

        self.assertEqual(unit, Decimal("87.4188"))
        self.assertEqual(money(unit * Decimal("67")), Decimal("5857.06"))

    def test_bdi_sale_unit_is_rounded_before_quantity(self):
        gross = money(Decimal("87.4188") * Decimal("1.430014"))
        unit = discounted_unit_price(gross)

        self.assertEqual(unit, Decimal("125.01"))
        self.assertEqual(money(unit * Decimal("47")), Decimal("5875.47"))

    def test_invalid_discounts(self):
        for discount in ("-1", "11", "0.001"):
            with self.assertRaises(ValidationError):
                discounted_unit_price(Decimal("10"), Decimal(discount))

    def test_zero_and_full_discount(self):
        self.assertEqual(discounted_unit_price(Decimal("10")), Decimal("10"))
        self.assertEqual(
            discounted_unit_price(Decimal("10"), Decimal("10")),
            Decimal("0"),
        )
