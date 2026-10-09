from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from budgeting.choices import (
    BudgetSheetItemType,
    BudgetSheetStatus,
    CompositionItemType,
    CompositionStatus,
    DataOrigin,
)
from budgeting.models import (
    BudgetSheet,
    BudgetSheetStage,
    BudgetSheetStageItem,
    BudgetStageCatalog,
    ServiceComposition,
    ServiceCompositionItem,
    ServiceCompositionVersion,
    Supply,
)
from budgeting.services.budget_sheet_exports import build_export_preview
from budgeting.services.budget_sheets import (
    apply_budget_item_reference_snapshot,
    finalize_budget_sheet,
    generate_budget_revision,
    recalculate_budget_totals,
)


class BudgetSheetExportWorkflowTests(TestCase):
    def setUp(self):
        self.stage_catalog = BudgetStageCatalog.objects.create(
            origin=DataOrigin.HUB,
            code="CC.01",
            name="CANTEIRO / DESPESAS INICIAIS",
            is_active=True,
        )
        self.supply = Supply.objects.create(
            origin=DataOrigin.HUB,
            description="AREIA MÉDIA",
            unit="M3",
            supply_type="MATERIAL",
            is_active=True,
        )
        self.composition = ServiceComposition.objects.create(
            origin=DataOrigin.HUB,
            code="COMP.001",
            name="ARGAMASSA DE ASSENTAMENTO",
            is_active=True,
        )
        self.version = ServiceCompositionVersion.objects.create(
            composition=self.composition,
            number=1,
            status=CompositionStatus.PUBLISHED,
            origin=DataOrigin.HUB,
            unit="M2",
            material_total=Decimal("20.0000"),
            labor_total=Decimal("10.0000"),
            equipment_total=Decimal("0.0000"),
            total=Decimal("30.0000"),
        )
        ServiceCompositionItem.objects.create(
            version=self.version,
            item_type=CompositionItemType.SUPPLY,
            supply=self.supply,
            description_snapshot="AREIA MÉDIA",
            unit_snapshot="M3",
            coefficient=Decimal("2.000000"),
            material_unit_price=Decimal("10.0000"),
            labor_unit_price=Decimal("0.0000"),
            equipment_unit_price=Decimal("0.0000"),
            position=1,
        )
        self.sheet = BudgetSheet.objects.create(
            number="25104-00",
            revision=0,
            reference_date="2026-09-02",
            considerations="Teste crítico",
            status=BudgetSheetStatus.DRAFT,
        )

    def _complete_sheet(self):
        stage = BudgetSheetStage.objects.create(
            budget_sheet=self.sheet,
            stage=self.stage_catalog,
            order=1,
            name_snapshot=self.stage_catalog.name,
        )
        item = BudgetSheetStageItem(
            budget_sheet_stage=stage,
            order=1,
            item_type=BudgetSheetItemType.SERVICE_COMPOSITION,
            service_composition=self.composition,
            quantity=Decimal("3"),
            unit_price=Decimal("50"),
        )
        apply_budget_item_reference_snapshot(item)
        item.save()
        recalculate_budget_totals(self.sheet.pk)
        self.sheet.refresh_from_db()
        return stage, item

    def test_cannot_finalize_empty_sheet(self):
        with self.assertRaises(ValidationError):
            finalize_budget_sheet(self.sheet.pk, user=None)

    def test_uses_raw_quantity_and_rounds_each_line_like_excel(self):
        stage = BudgetSheetStage.objects.create(
            budget_sheet=self.sheet,
            stage=self.stage_catalog,
            order=1,
            name_snapshot=self.stage_catalog.name,
        )
        item = BudgetSheetStageItem.objects.create(
            budget_sheet_stage=stage,
            order=1,
            item_type=BudgetSheetItemType.FREE_TEXT,
            description_snapshot="DEMOLIÇÃO DO PISO DE CONCRETO",
            unit_snapshot="M2",
            quantity=Decimal("3.2375"),
            unit_price=Decimal("98.97"),
        )

        recalculate_budget_totals(self.sheet.pk)
        item.refresh_from_db()
        stage.refresh_from_db()
        self.sheet.refresh_from_db()

        # Excel: ARRED(98,97 * (1,75 * 1,85); 2) = 320,42.
        self.assertEqual(item.quantity, Decimal("3.237500"))
        self.assertEqual(item.subtotal, Decimal("320.4200"))
        self.assertEqual(stage.subtotal, Decimal("320.42"))
        self.assertEqual(self.sheet.total_amount, Decimal("320.42"))

    def test_preserves_four_decimal_unit_price_before_rounding_line_total(self):
        stage = BudgetSheetStage.objects.create(
            budget_sheet=self.sheet,
            stage=self.stage_catalog,
            order=1,
            name_snapshot=self.stage_catalog.name,
        )
        item = BudgetSheetStageItem.objects.create(
            budget_sheet_stage=stage,
            order=1,
            item_type=BudgetSheetItemType.SUPPLY,
            supply=self.supply,
            description_snapshot="SERVIÇO COM CUSTO DE QUATRO CASAS",
            unit_snapshot="M2",
            quantity=Decimal("67"),
            unit_cost=Decimal("87.4188"),
            material_unit_cost=Decimal("87.4188"),
            unit_price=Decimal("87.4188"),
            apply_bdi=False,
        )

        recalculate_budget_totals(self.sheet.pk)
        item.refresh_from_db()
        stage.refresh_from_db()
        self.sheet.refresh_from_db()

        # 87,4188 x 67 = 5.857,0596 -> ARRED(...; 2) = 5.857,06.
        # Arredondar antes para 87,42 produziria incorretamente 5.857,14.
        self.assertEqual(item.unit_price, Decimal("87.4188"))
        self.assertEqual(item.subtotal, Decimal("5857.0600"))
        self.assertEqual(stage.subtotal, Decimal("5857.06"))
        self.assertEqual(self.sheet.total_amount, Decimal("5857.06"))

    def test_model_save_preserves_four_decimal_unit_price(self):
        stage = BudgetSheetStage.objects.create(
            budget_sheet=self.sheet,
            stage=self.stage_catalog,
            order=1,
            name_snapshot=self.stage_catalog.name,
        )
        item = BudgetSheetStageItem.objects.create(
            budget_sheet_stage=stage,
            order=1,
            item_type=BudgetSheetItemType.SUPPLY,
            supply=self.supply,
            description_snapshot="SERVIÇO COM CUSTO DE QUATRO CASAS",
            unit_snapshot="M2",
            quantity=Decimal("67"),
            unit_cost=Decimal("87.4188"),
            material_unit_cost=Decimal("87.4188"),
            unit_price=Decimal("87.4188"),
            apply_bdi=False,
        )

        item.refresh_from_db()

        self.assertEqual(item.unit_price, Decimal("87.4188"))
        self.assertEqual(item.subtotal, Decimal("5857.0600"))

    def test_bdi_rounds_sale_unit_to_cents_before_quantity_like_xls(self):
        stage = BudgetSheetStage.objects.create(
            budget_sheet=self.sheet,
            stage=self.stage_catalog,
            order=1,
            name_snapshot=self.stage_catalog.name,
        )
        item = BudgetSheetStageItem.objects.create(
            budget_sheet_stage=stage,
            order=1,
            item_type=BudgetSheetItemType.SUPPLY,
            supply=self.supply,
            description_snapshot="SERVIÇO COM BDI",
            unit_snapshot="M2",
            quantity=Decimal("47"),
            unit_cost=Decimal("87.4188"),
            material_unit_cost=Decimal("87.4188"),
            unit_price=Decimal("87.4188"),
            apply_bdi=True,
        )
        self.sheet.bdi_configuration = {
            "configured": True,
            "calculated_factor": "1.430014000000",
        }
        self.sheet.save(update_fields=("bdi_configuration", "updated_at"))

        # Isola aqui a regra de aplicação do fator. A memória BDI possui testes
        # próprios; o importante é garantir a ordem ARRED(unitário) -> quantidade.
        with patch("budgeting.services.budget_costs.refresh_budget_sheet_bdi"):
            recalculate_budget_totals(self.sheet.pk)

        item.refresh_from_db()
        stage.refresh_from_db()
        self.sheet.refresh_from_db()

        self.assertEqual(item.unit_price, Decimal("125.0100"))
        self.assertEqual(item.subtotal, Decimal("5875.4700"))
        self.assertEqual(stage.subtotal, Decimal("5875.47"))
        self.assertEqual(self.sheet.total_amount, Decimal("5875.47"))

    def test_revision_preserves_precise_financial_snapshot(self):
        stage = BudgetSheetStage.objects.create(
            budget_sheet=self.sheet,
            stage=self.stage_catalog,
            order=1,
            name_snapshot=self.stage_catalog.name,
            subtotal=Decimal("5875.47"),
        )
        item = BudgetSheetStageItem.objects.create(
            budget_sheet_stage=stage,
            order=1,
            item_type=BudgetSheetItemType.SUPPLY,
            supply=self.supply,
            description_snapshot="SERVIÇO COM BDI PRECISO",
            unit_snapshot="M2",
            quantity=Decimal("47"),
            unit_cost=Decimal("87.4188"),
            material_unit_cost=Decimal("87.4188"),
            unit_price=Decimal("125.0100"),
            pricing_factor=Decimal("1.4300"),
            apply_bdi=True,
        )
        # No XLS, o BDI forma primeiro o preço de venda unitário em centavos:
        # ARRED(87,4188 x 1,430014; 2) = 125,01; 125,01 x 47 = 5.875,47.
        BudgetSheetStageItem.objects.filter(pk=item.pk).update(
            subtotal=Decimal("5875.4700"),
            pricing_factor=Decimal("1.4300"),
        )
        BudgetSheet.objects.filter(pk=self.sheet.pk).update(
            status=BudgetSheetStatus.FINALIZED,
            total_amount=Decimal("5875.47"),
        )

        revision = generate_budget_revision(
            self.sheet.pk,
            reason="Ajuste de escopo",
            user=None,
        )
        cloned = BudgetSheetStageItem.objects.get(
            budget_sheet_stage__budget_sheet=revision,
        )

        self.assertEqual(cloned.unit_price, Decimal("125.0100"))
        self.assertEqual(cloned.subtotal, Decimal("5875.4700"))
        self.assertEqual(cloned.pricing_factor, Decimal("1.4300"))

    def test_sums_line_totals_after_excel_rounding(self):
        stage = BudgetSheetStage.objects.create(
            budget_sheet=self.sheet,
            stage=self.stage_catalog,
            order=1,
            name_snapshot=self.stage_catalog.name,
        )

        for order in (1, 2):
            BudgetSheetStageItem.objects.create(
                budget_sheet_stage=stage,
                order=order,
                item_type=BudgetSheetItemType.FREE_TEXT,
                description_snapshot=f"Linha {order}",
                unit_snapshot="VB",
                quantity=Decimal("1"),
                unit_price=Decimal("0.005"),
            )

        recalculate_budget_totals(self.sheet.pk)
        stage.refresh_from_db()
        self.sheet.refresh_from_db()

        # ARRED(0,005; 2) + ARRED(0,005; 2) = 0,02.
        self.assertEqual(stage.subtotal, Decimal("0.02"))
        self.assertEqual(self.sheet.total_amount, Decimal("0.02"))

    def test_finalize_recalculates_cost_snapshot_and_locks_revision(self):
        stage, item = self._complete_sheet()

        finalized = finalize_budget_sheet(
            self.sheet.pk,
            user=None,
        )

        finalized.refresh_from_db()
        stage.refresh_from_db()
        item.refresh_from_db()

        self.assertEqual(
            finalized.status,
            BudgetSheetStatus.FINALIZED,
        )

        self.assertEqual(
            finalized.total_amount,
            Decimal("90.00"),
        )

        self.assertEqual(
            stage.subtotal,
            Decimal("90.00"),
        )

        self.assertEqual(
            item.subtotal,
            Decimal("90.0000"),
        )

        self.assertEqual(
            item.material_unit_cost,
            Decimal("20.0000"),
        )

        self.assertEqual(
            item.labor_unit_cost,
            Decimal("10.0000"),
        )

        self.assertEqual(
            item.equipment_unit_cost,
            Decimal("0.0000"),
        )

        self.assertEqual(
            item.unit_cost,
            Decimal("30.0000"),
        )

        self.assertEqual(
            item.unit_price,
            Decimal("30.00"),
        )

        self.assertEqual(
            item.pricing_factor,
            Decimal("1.0000"),
        )

        self.assertTrue(
            item.composition_snapshot,
        )

        snapshot_items = item.composition_snapshot.get(
            "items",
            [],
        )

        self.assertEqual(
            len(snapshot_items),
            1,
        )

        self.assertEqual(
            snapshot_items[0]["description_snapshot"],
            "AREIA MÉDIA",
        )

        self.assertEqual(
            snapshot_items[0].get("display_only"),
            False,
        )

        self.assertEqual(
            snapshot_items[0].get("enabled"),
            True,
        )

        self.assertEqual(
            snapshot_items[0]["subtotal"],
            "20.00",
        )

    def test_client_preview_never_exposes_internal_breakdown(self):
        self._complete_sheet()
        finalize_budget_sheet(self.sheet.pk, user=None)
        preview = build_export_preview(self.sheet.pk, "CLIENT")

        composition = preview["nodes"][0]["children"][0]
        self.assertEqual(composition["number"], "1.1")
        self.assertEqual(composition["children"], [])
        self.assertNotIn("material_unit_cost", composition)
        self.assertNotIn("labor_unit_cost", composition)
        self.assertNotIn("equipment_unit_cost", composition)

    def test_daruix_preview_contains_third_level_components(self):
        self._complete_sheet()
        finalize_budget_sheet(self.sheet.pk, user=None)
        preview = build_export_preview(self.sheet.pk, "DARUIX")

        leaf = preview["nodes"][0]["children"][0]["children"][0]
        self.assertEqual(leaf["number"], "1.1.1")
        self.assertEqual(leaf["description"], "AREIA MÉDIA")
        self.assertEqual(Decimal(leaf["quantity"]), Decimal("6"))
        self.assertIn("material_unit_cost", leaf)

    def test_revision_copies_snapshot_instead_of_live_composition(self):
        _, original_item = self._complete_sheet()
        finalize_budget_sheet(self.sheet.pk, user=None)
        original_item.refresh_from_db()
        original_snapshot = original_item.composition_snapshot

        self.version.material_total = Decimal("999")
        self.version.total = Decimal("999")
        self.version.save(
            update_fields=("material_total", "total", "updated_at")
        )

        revision = generate_budget_revision(
            self.sheet.pk,
            reason="Alteração de quantitativos",
            user=None,
        )
        copied_item = revision.stages.get().items.get()

        self.assertEqual(copied_item.composition_snapshot, original_snapshot)
        self.assertEqual(copied_item.material_unit_cost, Decimal("20.0000"))
        self.assertEqual(copied_item.unit_cost, Decimal("30.0000"))
        self.assertEqual(revision.revision, 1)
        self.assertEqual(revision.status, BudgetSheetStatus.DRAFT)

    def test_finalize_rejects_composition_without_snapshot(self):
        stage = BudgetSheetStage.objects.create(
            budget_sheet=self.sheet,
            stage=self.stage_catalog,
            order=1,
            name_snapshot=self.stage_catalog.name,
        )
        BudgetSheetStageItem.objects.create(
            budget_sheet_stage=stage,
            order=1,
            item_type=BudgetSheetItemType.SERVICE_COMPOSITION,
            service_composition=self.composition,
            description_snapshot=self.composition.name,
            unit_snapshot="M2",
            quantity=Decimal("1"),
            unit_price=Decimal("30"),
        )

        with self.assertRaises(ValidationError):
            finalize_budget_sheet(self.sheet.pk, user=None)
