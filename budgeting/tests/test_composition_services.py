from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from budgeting.choices import (
    CompositionItemType,
    CompositionStatus,
    DataOrigin,
    SupplyType,
)
from budgeting.models import ServiceComposition, Supply
from budgeting.services.compositions import (
    create_composition,
    new_version,
    publish,
    update_draft,
)


class CompositionServiceTests(TestCase):
    def setUp(self):
        self.supply = Supply.objects.create(
            origin=DataOrigin.HUB,
            description="Cimento",
            supply_type=SupplyType.MATERIAL,
            unit="KG",
        )

    def _composition_data(self):
        return {
            "code": "CMP-001",
            "name": "Concreto",
            "is_active": True,
            "unit": "M³",
            "items": [
                {
                    "item_type": CompositionItemType.SUPPLY,
                    "supply": self.supply,
                    "coefficient": Decimal("2.500000"),
                    "material_unit_price": Decimal("10.1250"),
                    "labor_unit_price": Decimal("2.0000"),
                    "equipment_unit_price": Decimal("1.0000"),
                }
            ],
        }

    def test_create_does_not_mutate_validated_data_and_recalculates_totals(self):
        validated_data = self._composition_data()

        composition = create_composition(validated_data)

        self.assertIn("items", validated_data)
        self.assertIn("unit", validated_data)
        version = composition.latest_version
        self.assertEqual(version.status, CompositionStatus.DRAFT)
        self.assertEqual(version.unit, "M³")
        self.assertEqual(version.material_total, Decimal("25.3125"))
        self.assertEqual(version.labor_total, Decimal("5.0000"))
        self.assertEqual(version.equipment_total, Decimal("2.5000"))
        self.assertEqual(version.total, Decimal("32.8125"))
        item = version.items.get()
        self.assertEqual(item.description_snapshot, "Cimento")
        self.assertEqual(item.unit_snapshot, "KG")

    def test_update_draft_does_not_mutate_validated_data(self):
        composition = create_composition(self._composition_data())
        validated_data = {"name": "Concreto estrutural", "unit": "m³"}

        update_draft(composition, validated_data)

        self.assertEqual(validated_data, {"name": "Concreto estrutural", "unit": "m³"})
        composition.refresh_from_db()
        self.assertEqual(composition.name, "Concreto estrutural")
        self.assertEqual(composition.latest_version.unit, "m³")

    def test_publish_and_new_version_copy_items(self):
        composition = create_composition(self._composition_data())

        published = publish(composition)
        draft = new_version(composition)

        self.assertEqual(published.status, CompositionStatus.PUBLISHED)
        self.assertEqual(draft.number, 2)
        self.assertEqual(draft.status, CompositionStatus.DRAFT)
        self.assertEqual(draft.items.count(), 1)
        self.assertEqual(draft.total, published.total)

    def test_legacy_composition_cannot_be_published(self):
        composition = ServiceComposition.objects.create(
            origin=DataOrigin.LEGACY,
            legacy_table="tblComposicaoDeServico",
            legacy_id=22,
            name="Composição histórica",
        )

        with self.assertRaises(ValidationError):
            publish(composition)
