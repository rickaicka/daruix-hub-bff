from copy import deepcopy
from decimal import Decimal

from types import SimpleNamespace
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from budgeting.choices import BudgetSheetItemType, BudgetSheetStatus, SupplyType
from budgeting.models import BudgetSheet, BudgetSheetStage, BudgetSheetStageItem, BudgetStageCatalog, Supply
from budgeting.serializers import BudgetCompositionCustomizationSerializer
from budgeting.services.budget_composition_customization import customize_budget_composition
from budgeting.services.budget_sheets import build_composition_snapshot, finalize_budget_sheet, generate_budget_revision, recalculate_budget_totals
from budgeting.services.compositions import create_composition


class BudgetCompositionCustomizationTests(TestCase):
    def setUp(self):
        self.supply = Supply.objects.create(description="Bloco", supply_type=SupplyType.MATERIAL, unit="UN")
        self.composition = self.make_composition("Vedos", "10.00000000")
        self.sheet = BudgetSheet.objects.create(number="CUSTOM-00")
        self.stage = BudgetSheetStage.objects.create(
            budget_sheet=self.sheet, stage=BudgetStageCatalog.objects.create(name="Etapa"), order=1,
        )
        self.item = self.make_item(self.stage)
        self.other_sheet = BudgetSheet.objects.create(number="OTHER-00")
        other_stage = BudgetSheetStage.objects.create(budget_sheet=self.other_sheet, stage=self.stage.stage, order=1)
        self.other_item = self.make_item(other_stage)
        self.catalog_before = deepcopy(build_composition_snapshot(self.composition))
        self.other_before = deepcopy(self.other_item.composition_snapshot)

    def make_composition(self, name, price):
        return create_composition({"name": name, "unit": "VB", "items": [{
            "item_type": "SUPPLY", "supply": self.supply, "coefficient": Decimal("1"),
            "material_unit_price": Decimal(price), "labor_unit_price": Decimal("0"),
            "equipment_unit_price": Decimal("0"),
        }]})

    def make_item(self, stage):
        snap = build_composition_snapshot(self.composition)
        item = BudgetSheetStageItem.objects.create(
            budget_sheet_stage=stage, service_composition=self.composition,
            item_type=BudgetSheetItemType.SERVICE_COMPOSITION, description_snapshot=self.composition.name,
            unit_snapshot="VB", composition_version_number=snap["version_number"], composition_snapshot=snap,
            quantity=Decimal("2"), unit_cost=Decimal(snap["total"]), unit_price=Decimal(snap["total"]),
            material_unit_cost=Decimal(snap["material_total"]), order=1,
        )
        recalculate_budget_totals(stage.budget_sheet_id)
        item.refresh_from_db()
        return item

    def payload(self, **changes):
        self.item.refresh_from_db()
        data = {"expected_snapshot": deepcopy(self.item.composition_snapshot), "expected_quantity": str(self.item.quantity),
                "updates": [], "removed_paths": [], "additions": []}
        data.update(changes)
        return data

    def customize(self, payload):
        serializer = BudgetCompositionCustomizationSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        return customize_budget_composition(self.item, serializer.validated_data)

    def test_cost_and_effective_quantity_change_only_this_budget(self):
        updated = self.customize(self.payload(updates=[{"source_path": "1", "quantity": "6", "material_unit_price": "12.34567890"}]))
        self.assertEqual(updated.composition_snapshot["items"][0]["coefficient"], "3.000000000000000000")
        self.assertEqual(updated.composition_snapshot["items"][0]["material_unit_price"], "12.34567890")
        self.assertEqual(updated.unit_cost, Decimal("37.0370"))
        self.assertEqual(updated.subtotal, Decimal("74.07"))
        self.sheet.refresh_from_db(); self.stage.refresh_from_db(); self.other_item.refresh_from_db()
        self.assertEqual(self.sheet.total_amount, updated.subtotal)
        self.assertEqual(self.stage.subtotal, updated.subtotal)
        self.assertEqual(self.other_item.composition_snapshot, self.other_before)
        self.assertEqual(build_composition_snapshot(self.composition), self.catalog_before)

    def test_preserves_unit_precision_before_parent_quantity(self):
        self.item.quantity = Decimal("67"); self.item.save()
        updated = self.customize(self.payload(updates=[{"source_path": "1", "material_unit_price": "87.4188"}]))
        self.assertEqual(updated.unit_cost, Decimal("87.4188"))
        self.assertEqual(updated.subtotal, Decimal("5857.06"))

    def test_replace_one_component_with_three_in_one_transaction(self):
        additions = [{"item_type": "SUPPLY", "supply": self.supply.pk, "quantity": str(q), "material_unit_price": "2.5"} for q in (1, 2, 3)]
        updated = self.customize(self.payload(removed_paths=["1"], additions=additions))
        self.assertEqual([c["source_path"] for c in updated.composition_snapshot["items"]], ["2", "3", "4"])
        self.assertEqual(updated.subtotal, Decimal("15.00"))
        self.assertEqual(self.composition.latest_version.items.count(), 1)

    def test_subcomposition_copies_tree_then_can_edit_its_leaves(self):
        child = self.make_composition("Sub", "20")
        updated = self.customize(self.payload(additions=[{"item_type": "SUBCOMPOSITION", "subcomposition": child.pk, "quantity": "6"}]))
        self.assertEqual([c["source_path"] for c in updated.composition_snapshot["items"]], ["1", "2", "2.1"])
        self.assertEqual(updated.subtotal, Decimal("140.00"))
        updated = self.customize(self.payload(updates=[{"source_path": "2.1", "material_unit_price": "30"}]))
        self.assertEqual(updated.subtotal, Decimal("200.00"))
        self.assertEqual(child.latest_version.items.get().material_unit_price, Decimal("20"))
        updated = self.customize(self.payload(removed_paths=["2"]))
        self.assertEqual([c["source_path"] for c in updated.composition_snapshot["items"]], ["1"])

    def test_can_add_leaf_inside_existing_group(self):
        child = self.make_composition("Sub", "20")
        self.customize(self.payload(additions=[{"item_type": "SUBCOMPOSITION", "subcomposition": child.pk, "quantity": "2"}]))
        updated = self.customize(self.payload(additions=[{"item_type": "FREE_TEXT", "parent_path": "2", "description_snapshot": "Auxiliar", "quantity": "4", "labor_unit_price": "5"}]))
        self.assertEqual(updated.composition_snapshot["items"][-1]["source_path"], "2.2")
        self.assertEqual(updated.subtotal, Decimal("80.00"))

    def test_quantity_still_scales_with_parent(self):
        updated = self.customize(self.payload(updates=[{"source_path": "1", "quantity": "6"}]))
        updated.quantity = Decimal("4"); updated.save()
        recalculate_budget_totals(self.sheet.pk); updated.refresh_from_db()
        self.assertEqual(updated.subtotal, Decimal("120.00"))

    def test_noop_keeps_snapshot_and_totals_literal(self):
        data = self.payload(); before = deepcopy(self.item.composition_snapshot)
        updated = self.customize(data)
        self.assertEqual(updated.composition_snapshot, before)
        self.assertNotIn("customized", updated.composition_snapshot)

    def test_stale_snapshot_or_parent_quantity_is_rejected(self):
        data = self.payload(updates=[{"source_path": "1", "material_unit_price": "30"}])
        self.customize(self.payload(updates=[{"source_path": "1", "material_unit_price": "20"}]))
        with self.assertRaises(ValidationError): self.customize(data)
        data = self.payload()
        BudgetSheetStageItem.objects.filter(pk=self.item.pk).update(quantity=Decimal("3"))
        with self.assertRaises(ValidationError): self.customize(data)

    def test_invalid_and_foreign_paths_are_rejected(self):
        for change in ({"updates": [{"source_path": "99", "material_unit_price": "20"}]}, {"removed_paths": ["99"]}):
            with self.assertRaises(ValidationError): self.customize(self.payload(**change))
        self.item.refresh_from_db()
        self.assertEqual(self.item.composition_snapshot, self.catalog_before)

    def test_cannot_remove_all_components_or_add_self(self):
        with self.assertRaises(ValidationError): self.customize(self.payload(removed_paths=["1"]))
        with self.assertRaises(ValidationError): self.customize(self.payload(additions=[{"item_type": "SUBCOMPOSITION", "subcomposition": self.composition.pk, "quantity": "1"}]))

    def test_negative_excess_precision_and_reference_mismatch_are_rejected(self):
        for changes in (
            {"updates": [{"source_path": "1", "material_unit_price": "-1"}]},
            {"updates": [{"source_path": "1", "quantity": "1.0000001"}]},
            {"updates": [{"source_path": "1", "material_unit_price": "1.123456789"}]},
            {"additions": [{"item_type": "SUPPLY", "quantity": "1"}]},
        ):
            serializer = BudgetCompositionCustomizationSerializer(data=self.payload(**changes))
            self.assertFalse(serializer.is_valid())

    def test_failure_during_repricing_rolls_back_customization(self):
        self.item.unit_discount = Decimal("9"); self.item.save()
        with self.assertRaises(ValidationError):
            self.customize(self.payload(updates=[{"source_path": "1", "material_unit_price": "1"}]))
        self.item.refresh_from_db()
        self.assertEqual(self.item.composition_snapshot, self.catalog_before)

    def test_finalized_revision_is_immutable_and_next_revision_keeps_customization(self):
        updated = self.customize(self.payload(updates=[{"source_path": "1", "material_unit_price": "12.3456"}]))
        before = deepcopy(updated.composition_snapshot)
        finalize_budget_sheet(self.sheet.pk)
        with self.assertRaises(ValidationError): self.customize(self.payload())
        revision = generate_budget_revision(self.sheet.pk, reason="Nova revisão")
        clone = revision.stages.get().items.get()
        self.assertEqual(clone.composition_snapshot, before)
        self.item = clone
        self.customize(self.payload(updates=[{"source_path": "1", "material_unit_price": "25"}]))
        updated.refresh_from_db()
        self.assertEqual(updated.composition_snapshot, before)

    def test_bdi_and_discount_are_reapplied_after_customization(self):
        self.sheet.bdi_configuration = {"configured": True, "rows": [{"key": "lucro", "values": {"percentage": "10"}}]}
        self.sheet.save()
        self.item.apply_bdi = True; self.item.unit_discount = Decimal("1"); self.item.save()
        updated = self.customize(self.payload(updates=[{"source_path": "1", "material_unit_price": "20"}]))
        self.sheet.refresh_from_db()
        factor = Decimal(self.sheet.bdi_configuration["calculated_factor"])
        gross = (updated.unit_cost * factor).quantize(Decimal("0.01"))
        self.assertEqual(updated.unit_price, gross - Decimal("1"))
        self.assertEqual(updated.subtotal, (updated.quantity * (gross - Decimal("1"))).quantize(Decimal("0.01")))
        self.assertTrue(updated.apply_bdi)

    def test_endpoint_is_scoped_to_sheet_stage_and_item(self):
        client = APIClient()
        user = SimpleNamespace(is_authenticated=True)
        client.force_authenticate(user=user)
        url = f"/api/budgeting/budget-sheets/{self.sheet.pk}/stages/{self.stage.pk}/items/{self.item.pk}/components/customize/"
        response = client.patch(url, self.payload(updates=[{"source_path": "1", "material_unit_price": "11"}]), format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["composition_snapshot"]["customized"])
        wrong = url.replace(f"items/{self.item.pk}/", f"items/{self.other_item.pk}/")
        response = client.patch(wrong, self.payload(), format="json")
        self.assertEqual(response.status_code, 400)
