from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from budgeting.choices import (
    BudgetSheetItemType,
    BudgetSheetStatus,
    CompositionItemType,
    CompositionStatus,
    DataOrigin,
    SupplyType,
)
from budgeting.models import (
    BudgetSheet,
    BudgetSheetStage,
    BudgetSheetStageItem,
    BudgetStageCatalog,
    MaterialGroup,
    ServiceComposition,
    Supply,
)
from budgeting.services.budget_sheets import recalculate_budget_totals
from budgeting.views import (
    BudgetSheetViewSet,
    BudgetStageCatalogViewSet,
    SupplyViewSet,
)
from commercial.models import Party, CatalogOrigin, PersonType, Proposal


class SupplyApiTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory(HTTP_HOST="localhost")
        self.user = SimpleNamespace(is_authenticated=True)

    def _get(self, path: str, action: str):
        request = self.factory.get(path)
        force_authenticate(request, user=self.user)
        view = SupplyViewSet.as_view({"get": action})
        return view(request)

    def test_list_applies_search_and_page_size(self):
        Supply.objects.create(
            description="Estrutura metálica",
            supply_type=SupplyType.MATERIAL,
        )
        Supply.objects.create(
            description="Perfil metálico",
            supply_type=SupplyType.MATERIAL,
        )
        Supply.objects.create(
            description="Cimento Portland",
            supply_type=SupplyType.MATERIAL,
        )

        response = self._get(
            "/api/budgeting/supplies/?search=met&page_size=1",
            "list",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 1)

    def test_autocomplete_returns_only_active_matches(self):
        expected = Supply.objects.create(
            description="Estrutura metálica",
            supply_type=SupplyType.MATERIAL,
        )
        Supply.objects.create(
            description="Estrutura metálica inativa",
            supply_type=SupplyType.MATERIAL,
            is_active=False,
        )
        Supply.objects.create(
            description="Cimento Portland",
            supply_type=SupplyType.MATERIAL,
        )

        response = self._get(
            "/api/budgeting/supplies/autocomplete/?search=met",
            "autocomplete",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], expected.pk)

    def test_autocomplete_supports_incremental_pagination(self):
        supplies = [
            Supply.objects.create(
                description=f"Perfil metálico {index:02d}",
                supply_type=SupplyType.MATERIAL,
            )
            for index in range(25)
        ]

        first_page = self._get(
            ("/api/budgeting/supplies/autocomplete/?search=perfil&page=1&page_size=10"),
            "autocomplete",
        )
        second_page = self._get(
            ("/api/budgeting/supplies/autocomplete/?search=perfil&page=2&page_size=10"),
            "autocomplete",
        )

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(first_page.data["count"], 25)
        self.assertEqual(len(first_page.data["results"]), 10)
        self.assertIsNotNone(first_page.data["next"])

        self.assertEqual(second_page.status_code, 200)
        self.assertEqual(len(second_page.data["results"]), 10)

        first_ids = {item["id"] for item in first_page.data["results"]}
        second_ids = {item["id"] for item in second_page.data["results"]}
        self.assertTrue(first_ids.isdisjoint(second_ids))
        self.assertEqual(
            first_ids | second_ids,
            {supply.id for supply in supplies[:20]},
        )

    def test_legacy_supply_cannot_be_deleted(self):
        supply = Supply.objects.create(
            origin=DataOrigin.LEGACY,
            legacy_table="tblInsumos",
            legacy_id=10,
            description="Insumo legado",
        )
        request = self.factory.delete(f"/api/budgeting/supplies/{supply.pk}/")
        force_authenticate(request, user=self.user)
        view = SupplyViewSet.as_view({"delete": "destroy"})

        response = view(request, pk=supply.pk)

        self.assertEqual(response.status_code, 400)
        supply.refresh_from_db()
        self.assertTrue(supply.is_active)

    def test_autocomplete_filters_by_supply_type(self):
        material = Supply.objects.create(
            description="Perfil metálico",
            supply_type=SupplyType.MATERIAL,
        )

        Supply.objects.create(
            description="Perfil metálico serviço",
            supply_type=SupplyType.SERVICE,
        )

        response = self._get(
            (
                "/api/budgeting/supplies/autocomplete/"
                "?search=perfil"
                "&supply_type=MATERIAL"
            ),
            "autocomplete",
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.data["count"],
            1,
        )

        self.assertEqual(
            response.data["results"][0]["id"],
            material.pk,
        )

    def test_autocomplete_filters_by_material_group(self):
        electrical_group = MaterialGroup.objects.create(
            legacy_id=1,
            nome="Material Elétrico",
        )

        hydraulic_group = MaterialGroup.objects.create(
            legacy_id=2,
            nome="Material Hidráulico",
        )

        expected = Supply.objects.create(
            description="Cabo elétrico",
            supply_type=SupplyType.MATERIAL,
            material_group=electrical_group,
        )

        Supply.objects.create(
            description="Cabo hidráulico",
            supply_type=SupplyType.MATERIAL,
            material_group=hydraulic_group,
        )

        response = self._get(
            (
                "/api/budgeting/supplies/autocomplete/"
                "?search=cabo"
                f"&material_group={electrical_group.pk}"
            ),
            "autocomplete",
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.data["count"],
            1,
        )

        self.assertEqual(
            response.data["results"][0]["id"],
            expected.pk,
        )

    def test_autocomplete_combines_filters(self):
        electrical_group = MaterialGroup.objects.create(
            legacy_id=1,
            nome="Material Elétrico",
        )

        expected = Supply.objects.create(
            origin=DataOrigin.LEGACY,
            legacy_table="tblInsumos",
            legacy_id=100,
            description="Cabo elétrico flexível",
            supply_type=SupplyType.MATERIAL,
            material_group=electrical_group,
        )

        Supply.objects.create(
            description="Cabo elétrico serviço",
            supply_type=SupplyType.SERVICE,
            material_group=electrical_group,
        )

        response = self._get(
            (
                "/api/budgeting/supplies/autocomplete/"
                "?search=cabo"
                "&origin=LEGACY"
                "&supply_type=MATERIAL"
                f"&material_group={electrical_group.pk}"
            ),
            "autocomplete",
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.data["count"],
            1,
        )

        self.assertEqual(
            response.data["results"][0]["id"],
            expected.pk,
        )

class BudgetStageCatalogApiTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory(
            HTTP_HOST="localhost",
        )
        self.user = SimpleNamespace(
            is_authenticated=True,
        )

    def test_lists_and_filters_active_stages(self):
        expected = BudgetStageCatalog.objects.create(
            origin=DataOrigin.HUB,
            name="CANTEIRO DE OBRAS",
        )
        BudgetStageCatalog.objects.create(
            origin=DataOrigin.HUB,
            name="CANTEIRO INATIVO",
            is_active=False,
        )
        BudgetStageCatalog.objects.create(
            origin=DataOrigin.HUB,
            name="ADMINISTRAÇÃO",
        )

        request = self.factory.get(
            (
                "/api/budgeting/stages/"
                "?search=canteiro"
                "&is_active=true"
                "&page_size=10"
            )
        )
        force_authenticate(
            request,
            user=self.user,
        )

        view = BudgetStageCatalogViewSet.as_view(
            {"get": "list"}
        )
        response = view(request)

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            response.data["count"],
            1,
        )
        self.assertEqual(
            response.data["results"][0]["id"],
            expected.pk,
        )

    def test_creates_hub_stage(self):
        request = self.factory.post(
            "/api/budgeting/stages/",
            {
                "name": "Pavimento térreo",
                "code": "1.4",
                "legacy_category": "OPERATIONAL",
                "is_active": False,
                "origin": DataOrigin.LEGACY,
                "legacy_id": 999,
            },
            format="json",
        )
        force_authenticate(
            request,
            user=self.user,
        )

        view = BudgetStageCatalogViewSet.as_view(
            {"post": "create"}
        )
        response = view(request)

        self.assertEqual(response.status_code, 201)

        created = BudgetStageCatalog.objects.get(
            pk=response.data["id"],
        )
        self.assertEqual(created.name, "Pavimento térreo")
        self.assertEqual(created.code, "1.4")
        self.assertEqual(created.origin, DataOrigin.HUB)
        self.assertEqual(created.legacy_category, "OPERATIONAL")
        self.assertEqual(created.legacy_source, "")
        self.assertIsNone(created.legacy_id)
        self.assertTrue(created.is_active)

    def test_rejects_duplicate_stage_name_ignoring_case(self):
        BudgetStageCatalog.objects.create(
            origin=DataOrigin.HUB,
            name="Pavimento térreo",
        )
        request = self.factory.post(
            "/api/budgeting/stages/",
            {
                "name": "pavimento térreo",
                "legacy_category": "OPERATIONAL",
            },
            format="json",
        )
        force_authenticate(
            request,
            user=self.user,
        )

        view = BudgetStageCatalogViewSet.as_view(
            {"post": "create"}
        )
        response = view(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)

    def test_rejects_invalid_hub_stage_category(self):
        request = self.factory.post(
            "/api/budgeting/stages/",
            {
                "name": "Pavimento térreo",
                "legacy_category": "INVALID",
            },
            format="json",
        )
        force_authenticate(
            request,
            user=self.user,
        )

        view = BudgetStageCatalogViewSet.as_view(
            {"post": "create"}
        )
        response = view(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("legacy_category", response.data)

class BudgetSheetApiTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory(
            HTTP_HOST="localhost",
        )
        self.user = SimpleNamespace(
            is_authenticated=True,
        )

        self.party = Party.objects.create(
            origin=CatalogOrigin.LEGACY,
            legacy_id=1000,
            legacy_key="p" * 64,
            person_type=PersonType.COMPANY,
            legal_name="Cliente Teste",
        )

        self.proposal = Proposal.objects.create(
            origin=CatalogOrigin.LEGACY,
            legacy_id=2000,
            legacy_key="q" * 64,
            code="PC25035",
            party=self.party,
            entry_date=date(2026, 9, 1),
            work_name="Obra Teste",
        )

    def _authenticate(self, request):
        force_authenticate(
            request,
            user=self.user,
        )
        return request

    def _create_budget_sheet_stage(self):
        budget_sheet = BudgetSheet.objects.create(
            proposal=self.proposal,
            revision=0,
            number="",
        )
        catalog_stage = BudgetStageCatalog.objects.create(
            origin=DataOrigin.HUB,
            name="SERVIÇOS PRELIMINARES",
        )
        sheet_stage = BudgetSheetStage.objects.create(
            budget_sheet=budget_sheet,
            stage=catalog_stage,
            order=1,
        )

        return budget_sheet, sheet_stage

    def _create_budget_service_composition(
        self,
        *,
        code: str,
        name: str,
        total: Decimal,
        unit: str = "VB",
    ):
        composition = ServiceComposition.objects.create(
            origin=DataOrigin.HUB,
            code=code,
            name=name,
        )
        version = composition.versions.create(
            number=1,
            status=CompositionStatus.DRAFT,
            origin=DataOrigin.HUB,
            unit=unit,
            total=total,
        )
        return composition, version

    def _create_finalized_budget_with_item(self):
        budget_sheet, sheet_stage = (
            self._create_budget_sheet_stage()
        )
        item = BudgetSheetStageItem.objects.create(
            budget_sheet_stage=sheet_stage,
            item_type=BudgetSheetItemType.FREE_TEXT,
            description_snapshot="Mobilização da obra",
            unit_snapshot="VB",
            quantity=Decimal("2.000000"),
            unit_price=Decimal("125.0000"),
            order=1,
        )
        sheet_stage.subtotal = Decimal("250.00")
        sheet_stage.save(update_fields=("subtotal", "updated_at"))
        budget_sheet.total_amount = Decimal("250.00")
        budget_sheet.status = BudgetSheetStatus.FINALIZED
        budget_sheet.save(
            update_fields=("total_amount", "status", "updated_at")
        )

        return budget_sheet, sheet_stage, item

    def test_creates_budget_from_proposal(self):
        request = self._authenticate(
            self.factory.post(
                "/api/budgeting/budget-sheets/",
                {
                    "proposal": self.proposal.pk,
                    "revision": 0,
                    "reference_date": "2026-09-01",
                    "considerations": (
                        "Condições consideradas no orçamento."
                    ),
                },
                format="json",
            )
        )

        view = BudgetSheetViewSet.as_view(
            {"post": "create"}
        )
        response = view(request)

        self.assertEqual(
            response.status_code,
            201,
        )

        budget_sheet = BudgetSheet.objects.get()

        self.assertEqual(
            budget_sheet.number,
            "25035-00",
        )
        self.assertEqual(
            budget_sheet.party,
            self.party,
        )
        self.assertEqual(
            response.data["party_name"],
            "Cliente Teste",
        )
        self.assertEqual(
            response.data["stage_count"],
            0,
        )

    def test_creates_second_independent_budget_for_same_proposal(self):
        view = BudgetSheetViewSet.as_view({"post": "create"})

        first_request = self._authenticate(
            self.factory.post(
                "/api/budgeting/budget-sheets/",
                {"proposal": self.proposal.pk, "reference_date": "2026-09-01"},
                format="json",
            )
        )
        second_request = self._authenticate(
            self.factory.post(
                "/api/budgeting/budget-sheets/",
                {"proposal": self.proposal.pk, "reference_date": "2026-09-02"},
                format="json",
            )
        )

        first_response = view(first_request)
        second_response = view(second_request)

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 201)

        first = BudgetSheet.objects.get(pk=first_response.data["id"])
        second = BudgetSheet.objects.get(pk=second_response.data["id"])

        self.assertEqual(first.number, "25035-00")
        self.assertEqual(first.proposal_sequence, 0)
        self.assertEqual(first.revision, 0)
        self.assertIsNone(first.revision_root_id)

        self.assertEqual(second.number, "25035-01")
        self.assertEqual(second.proposal_sequence, 1)
        self.assertEqual(second.revision, 0)
        self.assertIsNone(second.revision_root_id)

    def test_adds_service_composition_item_and_updates_totals(self):
        budget_sheet, sheet_stage = (
            self._create_budget_sheet_stage()
        )

        composition = ServiceComposition.objects.create(
            origin=DataOrigin.HUB,
            code="COMP-001",
            name="Locação da obra",
        )
        composition.versions.create(
            number=1,
            status=CompositionStatus.DRAFT,
            origin=DataOrigin.HUB,
            unit="VB",
            total=Decimal("1500.0000"),
        )

        request = self._authenticate(
            self.factory.post(
                (
                    f"/api/budgeting/budget-sheets/"
                    f"{budget_sheet.pk}/stages/"
                    f"{sheet_stage.pk}/items/"
                ),
                {
                    "item_type": (
                        BudgetSheetItemType
                        .SERVICE_COMPOSITION
                    ),
                    "service_composition": composition.pk,
                    "quantity": "2.000000",
                },
                format="json",
            )
        )

        view = BudgetSheetViewSet.as_view(
            {"post": "stage_items"}
        )
        response = view(
            request,
            pk=budget_sheet.pk,
            stage_id=sheet_stage.pk,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data["description_snapshot"],
            "Locação da obra",
        )
        self.assertEqual(
            response.data["unit_snapshot"],
            "VB",
        )
        self.assertEqual(
            Decimal(response.data["unit_price"]),
            Decimal("1500.0000"),
        )
        self.assertEqual(
            Decimal(response.data["subtotal"]),
            Decimal("3000.0000"),
        )

        sheet_stage.refresh_from_db()
        budget_sheet.refresh_from_db()

        self.assertEqual(
            sheet_stage.subtotal,
            Decimal("3000.00"),
        )
        self.assertEqual(
            budget_sheet.total_amount,
            Decimal("3000.00"),
        )

    def test_updates_composition_parent_quantity_without_mutating_component_snapshot(self):
        budget_sheet, sheet_stage = self._create_budget_sheet_stage()
        supply = Supply.objects.create(
            description="Projeto estrutural",
            supply_type=SupplyType.SERVICE,
            unit="VB",
        )
        composition = ServiceComposition.objects.create(
            origin=DataOrigin.HUB,
            code="COMP-EST",
            name="Projeto de estruturas e fundações",
        )
        version = composition.versions.create(
            number=1,
            status=CompositionStatus.DRAFT,
            origin=DataOrigin.HUB,
            unit="VB",
            material_total=Decimal("20.0000"),
            total=Decimal("20.0000"),
        )
        version.items.create(
            item_type=CompositionItemType.SUPPLY,
            supply=supply,
            description_snapshot="Projeto estrutural",
            unit_snapshot="VB",
            coefficient=Decimal("2.0000"),
            material_unit_price=Decimal("10.0000"),
            position=0,
        )

        create_request = self._authenticate(
            self.factory.post(
                (
                    f"/api/budgeting/budget-sheets/{budget_sheet.pk}/stages/"
                    f"{sheet_stage.pk}/items/"
                ),
                {
                    "item_type": BudgetSheetItemType.SERVICE_COMPOSITION,
                    "service_composition": composition.pk,
                    "quantity": "1.000000",
                    # Deve ser ignorado: a composição é a fonte de verdade.
                    "unit_price": "9999.0000",
                },
                format="json",
            )
        )
        create_view = BudgetSheetViewSet.as_view({"post": "stage_items"})
        create_response = create_view(
            create_request,
            pk=budget_sheet.pk,
            stage_id=sheet_stage.pk,
        )
        self.assertEqual(create_response.status_code, 201)
        item_id = create_response.data["id"]
        original_snapshot = create_response.data["composition_snapshot"]
        self.assertEqual(Decimal(create_response.data["unit_price"]), Decimal("20.00"))

        update_request = self._authenticate(
            self.factory.patch(
                (
                    f"/api/budgeting/budget-sheets/{budget_sheet.pk}/stages/"
                    f"{sheet_stage.pk}/items/{item_id}/"
                ),
                {
                    "quantity": "3.000000",
                    # Também não pode sobrescrever o valor congelado.
                    "unit_price": "8888.0000",
                },
                format="json",
            )
        )
        update_view = BudgetSheetViewSet.as_view({"patch": "stage_item_detail"})
        response = update_view(
            update_request,
            pk=budget_sheet.pk,
            stage_id=sheet_stage.pk,
            item_id=item_id,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(response.data["quantity"]), Decimal("3.000000"))
        self.assertEqual(Decimal(response.data["unit_price"]), Decimal("20.00"))
        self.assertEqual(Decimal(response.data["subtotal"]), Decimal("60.00"))
        self.assertEqual(response.data["composition_snapshot"], original_snapshot)

        component = response.data["composition_snapshot"]["items"][0]
        self.assertEqual(Decimal(component["coefficient"]), Decimal("2.0000"))
        self.assertEqual(Decimal(component["subtotal"]), Decimal("20.00"))

        budget_sheet.refresh_from_db()
        self.assertEqual(budget_sheet.total_amount, Decimal("60.00"))

        version.items.get().refresh_from_db()
        self.assertEqual(version.items.get().coefficient, Decimal("2.0000"))

    def _save_bdi_configuration(
        self,
        budget_sheet,
        *,
        administracao_central="0",
        lucro="0",
        imprevistos="0",
        comercial="0",
        seguros="0",
        reserva_tecnica="0",
        encargos_financeiros="0",
        ir_imposto_renda_lucro="0",
        cs_contribuicao_social_lucro="0",
        iss="0",
        pis="0",
        cofins="0",
        diferencas_impostos="0",
        imposto_sobre_lucro="0",
    ):
        rows = {
            "lucro": lucro,
            "ir_imposto_renda_lucro": ir_imposto_renda_lucro,
            "cs_contribuicao_social_lucro": cs_contribuicao_social_lucro,
            "iss": iss,
            "pis": pis,
            "cofins": cofins,
            "diferencas_impostos": diferencas_impostos,
            "imposto_sobre_lucro": imposto_sobre_lucro,
            "imprevistos": imprevistos,
            "comercial": comercial,
            "seguros": seguros,
            "reserva_tecnica": reserva_tecnica,
            "encargos_financeiros": encargos_financeiros,
            "administracao_central": administracao_central,
        }
        request = self._authenticate(
            self.factory.put(
                f"/api/budgeting/budget-sheets/{budget_sheet.pk}/cost-configuration/",
                {
                    "bdi": {
                        "rows": [
                            {"key": key, "values": {"percentage": value}}
                            for key, value in rows.items()
                        ],
                    }
                },
                format="json",
            )
        )
        view = BudgetSheetViewSet.as_view({"put": "cost_configuration"})
        return view(request, pk=budget_sheet.pk)

    def _save_di_configuration(
        self,
        budget_sheet,
        *,
        quantity="1",
        material="0",
        labor="0",
        row_key="01_01",
    ):
        request = self._authenticate(
            self.factory.put(
                f"/api/budgeting/budget-sheets/{budget_sheet.pk}/cost-configuration/",
                {
                    "di": {
                        "rows": [
                            {
                                "key": row_key,
                                "values": {
                                    "quantity": quantity,
                                    "material": material,
                                    "labor": labor,
                                },
                            }
                        ]
                    }
                },
                format="json",
            )
        )
        view = BudgetSheetViewSet.as_view({"put": "cost_configuration"})
        return view(request, pk=budget_sheet.pk)

    def test_rejects_bdi_on_composition_when_sheet_has_no_bdi_memory(self):
        budget_sheet, sheet_stage = self._create_budget_sheet_stage()
        composition = ServiceComposition.objects.create(
            origin=DataOrigin.HUB,
            code="COMP-BDI-NO-CONFIG",
            name="Composição sem memória BDI",
        )
        composition.versions.create(
            number=1,
            status=CompositionStatus.DRAFT,
            origin=DataOrigin.HUB,
            unit="VB",
            total=Decimal("100.0000"),
        )
        request = self._authenticate(
            self.factory.post(
                (
                    f"/api/budgeting/budget-sheets/{budget_sheet.pk}/stages/"
                    f"{sheet_stage.pk}/items/"
                ),
                {
                    "item_type": BudgetSheetItemType.SERVICE_COMPOSITION,
                    "service_composition": composition.pk,
                    "quantity": "1.000000",
                    "apply_bdi": True,
                },
                format="json",
            )
        )
        response = BudgetSheetViewSet.as_view({"post": "stage_items"})(
            request,
            pk=budget_sheet.pk,
            stage_id=sheet_stage.pk,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("apply_bdi", response.data)

    def test_saves_bdi_memory_and_applies_result_only_to_marked_composition(self):
        budget_sheet, sheet_stage = self._create_budget_sheet_stage()
        config_response = self._save_bdi_configuration(
            budget_sheet,
            administracao_central="5",
        )
        self.assertEqual(config_response.status_code, 200)
        self.assertTrue(config_response.data["bdi"]["configured"])
        self.assertEqual(
            Decimal(config_response.data["bdi"]["calculated_percentage"]),
            Decimal("0.0000"),
        )
        self.assertEqual(
            config_response.data["bdi"]["calculation_status"],
            "WAITING_DIRECT_COST",
        )

        budget_sheet.refresh_from_db()
        self.assertEqual(budget_sheet.bdi_percentage, Decimal("0.0000"))
        self.assertTrue(budget_sheet.bdi_configuration["configured"])

        composition = ServiceComposition.objects.create(
            origin=DataOrigin.HUB,
            code="COMP-BDI",
            name="Composição com BDI opcional",
        )
        composition.versions.create(
            number=1,
            status=CompositionStatus.DRAFT,
            origin=DataOrigin.HUB,
            unit="VB",
            total=Decimal("100.0000"),
        )

        create_request = self._authenticate(
            self.factory.post(
                (
                    f"/api/budgeting/budget-sheets/{budget_sheet.pk}/stages/"
                    f"{sheet_stage.pk}/items/"
                ),
                {
                    "item_type": BudgetSheetItemType.SERVICE_COMPOSITION,
                    "service_composition": composition.pk,
                    "quantity": "2.000000",
                    "apply_bdi": True,
                },
                format="json",
            )
        )
        response = BudgetSheetViewSet.as_view({"post": "stage_items"})(
            create_request,
            pk=budget_sheet.pk,
            stage_id=sheet_stage.pk,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Decimal(response.data["unit_price"]), Decimal("105.00"))
        self.assertEqual(Decimal(response.data["subtotal"]), Decimal("210.00"))

        item_id = response.data["id"]
        update_request = self._authenticate(
            self.factory.patch(
                (
                    f"/api/budgeting/budget-sheets/{budget_sheet.pk}/stages/"
                    f"{sheet_stage.pk}/items/{item_id}/"
                ),
                {"apply_bdi": False},
                format="json",
            )
        )
        response = BudgetSheetViewSet.as_view({"patch": "stage_item_detail"})(
            update_request,
            pk=budget_sheet.pk,
            stage_id=sheet_stage.pk,
            item_id=item_id,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(response.data["unit_price"]), Decimal("100.00"))

    def test_updating_bdi_memory_recalculates_existing_marked_compositions(self):
        budget_sheet, sheet_stage = self._create_budget_sheet_stage()
        self._save_bdi_configuration(budget_sheet, administracao_central="5")

        composition = ServiceComposition.objects.create(
            origin=DataOrigin.HUB,
            code="COMP-BDI-UPDATE",
            name="Composição recalculada pelo BDI",
        )
        version = composition.versions.create(
            number=1,
            status=CompositionStatus.DRAFT,
            origin=DataOrigin.HUB,
            unit="VB",
            total=Decimal("80.0000"),
        )
        item = BudgetSheetStageItem.objects.create(
            budget_sheet_stage=sheet_stage,
            item_type=BudgetSheetItemType.SERVICE_COMPOSITION,
            service_composition=composition,
            description_snapshot=composition.name,
            unit_snapshot=version.unit,
            composition_version_number=version.number,
            unit_cost=Decimal("80.0000"),
            quantity=Decimal("2.000000"),
            unit_price=Decimal("84.0000"),
            subtotal=Decimal("168.0000"),
            apply_bdi=True,
            order=1,
        )

        config_response = self._save_bdi_configuration(
            budget_sheet,
            administracao_central="12.5",
        )
        self.assertEqual(config_response.status_code, 200)
        self.assertEqual(
            Decimal(config_response.data["bdi"]["calculated_percentage"]),
            Decimal("12.5000"),
        )

        item.refresh_from_db()
        budget_sheet.refresh_from_db()
        self.assertEqual(item.unit_price, Decimal("90.0000"))
        self.assertEqual(item.subtotal, Decimal("180.0000"))
        self.assertEqual(budget_sheet.total_amount, Decimal("180.00"))

    def test_bdi_formula_uses_non_tax_base_with_large_direct_cost(self):
        budget_sheet, sheet_stage = self._create_budget_sheet_stage()
        composition = ServiceComposition.objects.create(
            origin=DataOrigin.HUB,
            code="COMP-BDI-PC25104",
            name="Base direta da planilha de referência",
        )
        version = composition.versions.create(
            number=1,
            status=CompositionStatus.DRAFT,
            origin=DataOrigin.HUB,
            unit="VB",
            total=Decimal("1943636.7900"),
        )
        BudgetSheetStageItem.objects.create(
            budget_sheet_stage=sheet_stage,
            item_type=BudgetSheetItemType.SERVICE_COMPOSITION,
            service_composition=composition,
            description_snapshot=composition.name,
            unit_snapshot=version.unit,
            composition_version_number=version.number,
            material_unit_cost=Decimal("918640.5300"),
            labor_unit_cost=Decimal("1024996.2600"),
            equipment_unit_cost=Decimal("0.0000"),
            unit_cost=Decimal("1943636.7900"),
            quantity=Decimal("1.000000"),
            unit_price=Decimal("1943636.7900"),
            subtotal=Decimal("1943636.7900"),
            apply_bdi=False,
            order=1,
        )
        recalculate_budget_totals(budget_sheet.pk)

        # Entradas históricas do PC25104 com a regra de gross-up do PC25017:
        # A=1.943.636,79; B=188.925,86; D=23%; F=18,71%.
        request = self._authenticate(
            self.factory.put(
                f"/api/budgeting/budget-sheets/{budget_sheet.pk}/cost-configuration/",
                {
                    "di": {
                        "rows": [
                            {
                                "key": "01_01",
                                "values": {
                                    "quantity": "1",
                                    "material": "23507.76",
                                    "labor": "165418.10",
                                },
                            }
                        ]
                    },
                    "bdi": {
                        "rows": [
                            {"key": "lucro", "values": {"percentage": "15"}},
                            {"key": "ir_imposto_renda_lucro", "values": {"percentage": "1.5"}},
                            {"key": "cs_contribuicao_social_lucro", "values": {"percentage": "1"}},
                            {"key": "iss", "values": {"percentage": "5"}},
                            {"key": "pis", "values": {"percentage": "0.65"}},
                            {"key": "cofins", "values": {"percentage": "3"}},
                            {"key": "diferencas_impostos", "values": {"percentage": "6.39"}},
                            {"key": "imposto_sobre_lucro", "values": {"percentage": "1.17"}},
                            {"key": "imprevistos", "values": {"percentage": "1"}},
                            {"key": "comercial", "values": {"percentage": "6"}},
                            {"key": "seguros", "values": {"percentage": "0"}},
                            {"key": "reserva_tecnica", "values": {"percentage": "0"}},
                            {"key": "encargos_financeiros", "values": {"percentage": "0"}},
                            {"key": "administracao_central", "values": {"percentage": "1"}},
                        ],
                    },
                },
                format="json",
            )
        )
        response = BudgetSheetViewSet.as_view({"put": "cost_configuration"})(
            request,
            pk=budget_sheet.pk,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Decimal(response.data["di"]["totals"]["material"]),
            Decimal("23507.76"),
        )
        self.assertEqual(
            Decimal(response.data["di"]["totals"]["labor"]),
            Decimal("165418.10"),
        )
        self.assertEqual(
            Decimal(response.data["bdi"]["summary"]["direct_cost"]["material"]),
            Decimal("918640.53"),
        )
        self.assertEqual(
            Decimal(response.data["bdi"]["summary"]["direct_cost"]["labor"]),
            Decimal("1024996.26"),
        )
        self.assertEqual(
            Decimal(response.data["bdi"]["calculated_percentage"]),
            Decimal("40.7642"),
        )
        self.assertEqual(
            Decimal(response.data["bdi"]["calculated_factor"]),
            Decimal("1.407642048966"),
        )

    def test_updating_di_recalculates_bdi_and_marked_compositions(self):
        budget_sheet, sheet_stage = self._create_budget_sheet_stage()
        self._save_bdi_configuration(
            budget_sheet,
            administracao_central="5",
        )

        composition = ServiceComposition.objects.create(
            origin=DataOrigin.HUB,
            code="COMP-DI-BDI",
            name="Composição dependente do D.I.",
        )
        version = composition.versions.create(
            number=1,
            status=CompositionStatus.DRAFT,
            origin=DataOrigin.HUB,
            unit="VB",
            total=Decimal("100.0000"),
        )
        item = BudgetSheetStageItem.objects.create(
            budget_sheet_stage=sheet_stage,
            item_type=BudgetSheetItemType.SERVICE_COMPOSITION,
            service_composition=composition,
            description_snapshot=composition.name,
            unit_snapshot=version.unit,
            composition_version_number=version.number,
            unit_cost=Decimal("100.0000"),
            quantity=Decimal("1.000000"),
            unit_price=Decimal("105.0000"),
            subtotal=Decimal("105.0000"),
            apply_bdi=True,
            order=1,
        )
        recalculate_budget_totals(budget_sheet.pk)

        response = self._save_di_configuration(
            budget_sheet,
            quantity="1",
            material="10",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Decimal(response.data["di"]["totals"]["total"]),
            Decimal("10.00"),
        )
        # Excel: A=100, B=10, D=5%*(A+B)=5,50, F=0, G=115,50.
        self.assertEqual(
            Decimal(response.data["bdi"]["calculated_percentage"]),
            Decimal("15.5000"),
        )

        item.refresh_from_db()
        budget_sheet.refresh_from_db()
        self.assertEqual(budget_sheet.bdi_percentage, Decimal("15.5000"))
        self.assertEqual(item.unit_price, Decimal("115.50"))
        self.assertEqual(item.subtotal, Decimal("115.50"))

    def test_di_uses_quantity_material_labor_and_calculated_columns(self):
        budget_sheet, _ = self._create_budget_sheet_stage()
        response = self._save_di_configuration(
            budget_sheet,
            quantity="2",
            material="10",
            labor="5",
        )
        self.assertEqual(response.status_code, 200)

        row = next(
            row for row in response.data["di"]["rows"]
            if row["key"] == "01_01"
        )
        self.assertEqual(Decimal(row["values"]["unit_price"]), Decimal("15.0000"))
        self.assertEqual(Decimal(row["values"]["total"]), Decimal("30.00"))
        self.assertEqual(Decimal(response.data["di"]["totals"]["material"]), Decimal("20.00"))
        self.assertEqual(Decimal(response.data["di"]["totals"]["labor"]), Decimal("10.00"))
        self.assertEqual(Decimal(response.data["di"]["totals"]["total"]), Decimal("30.00"))

    def test_di_configuration_can_be_read_after_calculated_columns_are_persisted(self):
        budget_sheet, _ = self._create_budget_sheet_stage()

        response = self._save_di_configuration(
            budget_sheet,
            quantity="2",
            material="10",
            labor="5",
        )
        self.assertEqual(response.status_code, 200)

        budget_sheet.refresh_from_db()
        stored_row = next(
            row
            for row in budget_sheet.di_configuration["rows"]
            if row["key"] == "01_01"
        )
        self.assertEqual(stored_row["values"]["unit_price"], "15.0000")
        self.assertEqual(stored_row["values"]["total"], "30.00")

        request = self._authenticate(
            self.factory.get(
                f"/api/budgeting/budget-sheets/{budget_sheet.pk}/cost-configuration/"
            )
        )
        response = BudgetSheetViewSet.as_view({"get": "cost_configuration"})(
            request,
            pk=budget_sheet.pk,
        )
        self.assertEqual(response.status_code, 200)
        row = next(
            row for row in response.data["di"]["rows"]
            if row["key"] == "01_01"
        )
        self.assertEqual(row["values"]["quantity"], "2.000000")
        self.assertEqual(row["values"]["material"], "10.0000")
        self.assertEqual(row["values"]["labor"], "5.0000")
        self.assertEqual(row["values"]["unit_price"], "15.0000")
        self.assertEqual(row["values"]["total"], "30.00")

    def test_di_configuration_persists_without_budget_sheet_model_save(self):
        budget_sheet, _ = self._create_budget_sheet_stage()

        # A configuração já é validada pelo serviço. Persisti-la não deve
        # executar novamente o full_clean() global de BudgetSheet.
        with patch.object(
            BudgetSheet,
            "save",
            side_effect=AssertionError("BudgetSheet.save não deve ser chamado"),
        ):
            response = self._save_di_configuration(
                budget_sheet,
                quantity="2",
                material="10",
                labor="5",
            )

        self.assertEqual(response.status_code, 200)
        budget_sheet.refresh_from_db()
        self.assertTrue(budget_sheet.di_configuration["configured"])
        self.assertEqual(
            Decimal(budget_sheet.di_configuration["totals"]["total"]),
            Decimal("30.00"),
        )

    def test_pc25104_encargos_financeiros_is_detail_only_not_part_of_d(self):
        budget_sheet, sheet_stage = self._create_budget_sheet_stage()
        composition = ServiceComposition.objects.create(
            origin=DataOrigin.HUB,
            code="COMP-BDI-ENCARGOS",
            name="Base para validar encargos financeiros",
        )
        version = composition.versions.create(
            number=1,
            status=CompositionStatus.DRAFT,
            origin=DataOrigin.HUB,
            unit="VB",
            total=Decimal("100.0000"),
        )
        BudgetSheetStageItem.objects.create(
            budget_sheet_stage=sheet_stage,
            item_type=BudgetSheetItemType.SERVICE_COMPOSITION,
            service_composition=composition,
            description_snapshot=composition.name,
            unit_snapshot=version.unit,
            composition_version_number=version.number,
            material_unit_cost=Decimal("100.0000"),
            labor_unit_cost=Decimal("0.0000"),
            equipment_unit_cost=Decimal("0.0000"),
            unit_cost=Decimal("100.0000"),
            quantity=Decimal("1.000000"),
            unit_price=Decimal("100.0000"),
            subtotal=Decimal("100.0000"),
            apply_bdi=False,
            order=1,
        )
        recalculate_budget_totals(budget_sheet.pk)

        response = self._save_bdi_configuration(
            budget_sheet,
            encargos_financeiros="10",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Decimal(response.data["bdi"]["summary"]["non_tax_percentage"]),
            Decimal("0.0000"),
        )
        self.assertEqual(
            Decimal(response.data["bdi"]["calculated_percentage"]),
            Decimal("0.0000"),
        )
        self.assertEqual(
            Decimal(response.data["bdi"]["detail_total_percentage"]),
            Decimal("10.0000"),
        )

    def test_cost_configuration_rejects_structural_fields(self):
        budget_sheet, _ = self._create_budget_sheet_stage()
        request = self._authenticate(
            self.factory.put(
                f"/api/budgeting/budget-sheets/{budget_sheet.pk}/cost-configuration/",
                {
                    "bdi": {
                        "rows": [
                            {
                                "key": "administracao_central",
                                "discrimination": "Tentativa de trocar label",
                                "values": {"percentage": "5"},
                            }
                        ]
                    }
                },
                format="json",
            )
        )
        response = BudgetSheetViewSet.as_view({"put": "cost_configuration"})(
            request,
            pk=budget_sheet.pk,
        )
        self.assertEqual(response.status_code, 400)

    def test_adds_free_text_item(self):
        budget_sheet, sheet_stage = (
            self._create_budget_sheet_stage()
        )

        request = self._authenticate(
            self.factory.post(
                (
                    f"/api/budgeting/budget-sheets/"
                    f"{budget_sheet.pk}/stages/"
                    f"{sheet_stage.pk}/items/"
                ),
                {
                    "item_type": (
                        BudgetSheetItemType.FREE_TEXT
                    ),
                    "description_snapshot": (
                        "Taxa de mobilização"
                    ),
                    "unit_snapshot": "VB",
                    "quantity": "1.000000",
                    "unit_price": "750.0000",
                },
                format="json",
            )
        )

        view = BudgetSheetViewSet.as_view(
            {"post": "stage_items"}
        )
        response = view(
            request,
            pk=budget_sheet.pk,
            stage_id=sheet_stage.pk,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["order"], 1)
        self.assertEqual(
            Decimal(response.data["subtotal"]),
            Decimal("750.0000"),
        )

    def test_updates_item_and_recalculates_totals(self):
        budget_sheet, sheet_stage = (
            self._create_budget_sheet_stage()
        )

        create_request = self._authenticate(
            self.factory.post(
                (
                    f"/api/budgeting/budget-sheets/"
                    f"{budget_sheet.pk}/stages/"
                    f"{sheet_stage.pk}/items/"
                ),
                {
                    "item_type": (
                        BudgetSheetItemType.FREE_TEXT
                    ),
                    "description_snapshot": "Mobilização",
                    "unit_snapshot": "VB",
                    "quantity": "1.000000",
                    "unit_price": "100.0000",
                },
                format="json",
            )
        )

        create_view = BudgetSheetViewSet.as_view(
            {"post": "stage_items"}
        )
        create_response = create_view(
            create_request,
            pk=budget_sheet.pk,
            stage_id=sheet_stage.pk,
        )

        item_id = create_response.data["id"]

        update_request = self._authenticate(
            self.factory.patch(
                (
                    f"/api/budgeting/budget-sheets/"
                    f"{budget_sheet.pk}/stages/"
                    f"{sheet_stage.pk}/items/"
                    f"{item_id}/"
                ),
                {
                    "quantity": "3.000000",
                    "unit_price": "125.0000",
                },
                format="json",
            )
        )

        update_view = BudgetSheetViewSet.as_view(
            {"patch": "stage_item_detail"}
        )
        update_response = update_view(
            update_request,
            pk=budget_sheet.pk,
            stage_id=sheet_stage.pk,
            item_id=item_id,
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(
            Decimal(update_response.data["subtotal"]),
            Decimal("375.0000"),
        )

        sheet_stage.refresh_from_db()
        budget_sheet.refresh_from_db()

        self.assertEqual(
            sheet_stage.subtotal,
            Decimal("375.00"),
        )
        self.assertEqual(
            budget_sheet.total_amount,
            Decimal("375.00"),
        )

    def test_deletes_item_compacts_order_and_recalculates(self):
        budget_sheet, sheet_stage = (
            self._create_budget_sheet_stage()
        )

        create_view = BudgetSheetViewSet.as_view(
            {"post": "stage_items"}
        )
        created_ids = []

        for description, price in (
                ("Primeiro item", "100.0000"),
                ("Segundo item", "200.0000"),
        ):
            request = self._authenticate(
                self.factory.post(
                    (
                        f"/api/budgeting/budget-sheets/"
                        f"{budget_sheet.pk}/stages/"
                        f"{sheet_stage.pk}/items/"
                    ),
                    {
                        "item_type": (
                            BudgetSheetItemType.FREE_TEXT
                        ),
                        "description_snapshot": description,
                        "unit_snapshot": "VB",
                        "quantity": "1.000000",
                        "unit_price": price,
                    },
                    format="json",
                )
            )
            response = create_view(
                request,
                pk=budget_sheet.pk,
                stage_id=sheet_stage.pk,
            )
            created_ids.append(response.data["id"])

        delete_request = self._authenticate(
            self.factory.delete(
                (
                    f"/api/budgeting/budget-sheets/"
                    f"{budget_sheet.pk}/stages/"
                    f"{sheet_stage.pk}/items/"
                    f"{created_ids[0]}/"
                )
            )
        )

        delete_view = BudgetSheetViewSet.as_view(
            {"delete": "stage_item_detail"}
        )
        response = delete_view(
            delete_request,
            pk=budget_sheet.pk,
            stage_id=sheet_stage.pk,
            item_id=created_ids[0],
        )

        self.assertEqual(response.status_code, 204)

        remaining_item = BudgetSheetStageItem.objects.get()
        self.assertEqual(remaining_item.order, 1)

        sheet_stage.refresh_from_db()
        budget_sheet.refresh_from_db()

        self.assertEqual(
            sheet_stage.subtotal,
            Decimal("200.00"),
        )
        self.assertEqual(
            budget_sheet.total_amount,
            Decimal("200.00"),
        )

    def test_adds_stages_with_automatic_order(self):
        budget_sheet = BudgetSheet.objects.create(
            proposal=self.proposal,
            revision=0,
            number="",
        )
        first_catalog_stage = (
            BudgetStageCatalog.objects.create(
                origin=DataOrigin.HUB,
                name="CANTEIRO DE OBRAS",
            )
        )
        second_catalog_stage = (
            BudgetStageCatalog.objects.create(
                origin=DataOrigin.HUB,
                name="FUNDAÇÕES",
            )
        )

        view = BudgetSheetViewSet.as_view(
            {"post": "stages"}
        )

        first_request = self._authenticate(
            self.factory.post(
                (
                    f"/api/budgeting/budget-sheets/"
                    f"{budget_sheet.pk}/stages/"
                ),
                {
                    "stage": first_catalog_stage.pk,
                    "notes": "Primeira etapa",
                },
                format="json",
            )
        )
        first_response = view(
            first_request,
            pk=budget_sheet.pk,
        )

        second_request = self._authenticate(
            self.factory.post(
                (
                    f"/api/budgeting/budget-sheets/"
                    f"{budget_sheet.pk}/stages/"
                ),
                {
                    "stage": second_catalog_stage.pk,
                },
                format="json",
            )
        )
        second_response = view(
            second_request,
            pk=budget_sheet.pk,
        )

        self.assertEqual(
            first_response.status_code,
            201,
        )
        self.assertEqual(
            second_response.status_code,
            201,
        )
        self.assertEqual(
            first_response.data["order"],
            1,
        )
        self.assertEqual(
            second_response.data["order"],
            2,
        )
        self.assertEqual(
            list(
                budget_sheet.stages.values_list(
                    "name_snapshot",
                    flat=True,
                )
            ),
            [
                "CANTEIRO DE OBRAS",
                "FUNDAÇÕES",
            ],
        )

    def test_rejects_duplicated_stage(self):
        budget_sheet = BudgetSheet.objects.create(
            proposal=self.proposal,
            revision=0,
            number="",
        )
        catalog_stage = BudgetStageCatalog.objects.create(
            origin=DataOrigin.HUB,
            name="CANTEIRO DE OBRAS",
        )
        BudgetSheetStage.objects.create(
            budget_sheet=budget_sheet,
            stage=catalog_stage,
            order=1,
        )

        request = self._authenticate(
            self.factory.post(
                (
                    f"/api/budgeting/budget-sheets/"
                    f"{budget_sheet.pk}/stages/"
                ),
                {
                    "stage": catalog_stage.pk,
                },
                format="json",
            )
        )

        view = BudgetSheetViewSet.as_view(
            {"post": "stages"}
        )
        response = view(
            request,
            pk=budget_sheet.pk,
        )

        self.assertEqual(
            response.status_code,
            400,
        )
        self.assertIn(
            "stage",
            response.data,
        )
        self.assertEqual(
            BudgetSheetStage.objects.count(),
            1,
        )

    def test_reorders_all_stages(self):
        budget_sheet = BudgetSheet.objects.create(
            proposal=self.proposal,
            revision=0,
            number="",
        )

        stages = [
            BudgetSheetStage.objects.create(
                budget_sheet=budget_sheet,
                stage=BudgetStageCatalog.objects.create(
                    origin=DataOrigin.HUB,
                    name=name,
                ),
                order=order,
            )
            for order, name in enumerate(
                (
                    "CANTEIRO",
                    "FUNDAÇÕES",
                    "ESTRUTURA",
                ),
                start=1,
            )
        ]

        requested_order = [
            stages[2].pk,
            stages[0].pk,
            stages[1].pk,
        ]

        request = self._authenticate(
            self.factory.post(
                (
                    f"/api/budgeting/budget-sheets/"
                    f"{budget_sheet.pk}/stages/reorder/"
                ),
                {
                    "stage_ids": requested_order,
                },
                format="json",
            )
        )

        view = BudgetSheetViewSet.as_view(
            {"post": "reorder_stages"}
        )
        response = view(
            request,
            pk=budget_sheet.pk,
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            [
                item["id"]
                for item in response.data
            ],
            requested_order,
        )
        self.assertEqual(
            list(
                budget_sheet.stages
                .order_by("order")
                .values_list(
                    "order",
                    flat=True,
                )
            ),
            [1, 2, 3],
        )

    def test_deleting_stage_compacts_orders(self):
        budget_sheet = BudgetSheet.objects.create(
            proposal=self.proposal,
            revision=0,
            number="",
        )

        stages = [
            BudgetSheetStage.objects.create(
                budget_sheet=budget_sheet,
                stage=BudgetStageCatalog.objects.create(
                    origin=DataOrigin.HUB,
                    name=f"ETAPA {order}",
                ),
                order=order,
            )
            for order in range(1, 4)
        ]

        request = self._authenticate(
            self.factory.delete(
                (
                    f"/api/budgeting/budget-sheets/"
                    f"{budget_sheet.pk}/stages/"
                    f"{stages[1].pk}/"
                )
            )
        )

        view = BudgetSheetViewSet.as_view(
            {"delete": "stage_detail"}
        )
        response = view(
            request,
            pk=budget_sheet.pk,
            stage_id=stages[1].pk,
        )

        self.assertEqual(
            response.status_code,
            204,
        )
        self.assertEqual(
            list(
                budget_sheet.stages
                .order_by("order")
                .values_list(
                    "order",
                    flat=True,
                )
            ),
            [1, 2],
        )

    def test_generates_revision_with_stage_and_item_snapshots(self):
        source, source_stage, source_item = (
            self._create_finalized_budget_with_item()
        )
        source.bdi_percentage = Decimal("7.5000")
        source.bdi_configuration = {
            "version": 3,
            "configured": True,
            "rows": [
                {
                    "key": "administracao_central",
                    "values": {"percentage": "7.5000"},
                }
            ],
        }
        source.di_configuration = {
            "version": 3,
            "configured": True,
            "rows": [
                {
                    "key": "04_01",
                    "values": {
                        "quantity": "1.000000",
                        "material": "0.0000",
                        "labor": "1000.0000",
                    },
                }
            ],
        }
        source.save(
            update_fields=(
                "bdi_percentage",
                "bdi_configuration",
                "di_configuration",
                "updated_at",
            )
        )
        request = self._authenticate(
            self.factory.post(
                (
                    f"/api/budgeting/budget-sheets/"
                    f"{source.pk}/generate-revision/"
                ),
                {
                    "reason": (
                        "Ajuste de quantitativos e inclusão de serviços."
                    )
                },
                format="json",
            )
        )
        view = BudgetSheetViewSet.as_view(
            {"post": "generate_revision"}
        )
        response = view(request, pk=source.pk)

        self.assertEqual(response.status_code, 201)
        revision = BudgetSheet.objects.get(revision=1)
        self.assertEqual(revision.number, "25035-00")
        self.assertEqual(revision.status, BudgetSheetStatus.DRAFT)
        self.assertEqual(revision.revision_root, source)
        self.assertEqual(revision.previous_revision, source)
        self.assertEqual(revision.total_amount, Decimal("250.00"))
        self.assertEqual(revision.bdi_percentage, source.bdi_percentage)
        self.assertEqual(revision.bdi_configuration, source.bdi_configuration)
        self.assertEqual(revision.di_configuration, source.di_configuration)
        self.assertEqual(revision.stages.count(), 1)

        revision_stage = revision.stages.get()
        revision_item = revision_stage.items.get()
        self.assertNotEqual(revision_stage.pk, source_stage.pk)
        self.assertNotEqual(revision_item.pk, source_item.pk)
        self.assertEqual(
            revision_stage.name_snapshot,
            source_stage.name_snapshot,
        )
        self.assertEqual(
            revision_item.description_snapshot,
            source_item.description_snapshot,
        )
        self.assertEqual(revision_item.origin, DataOrigin.HUB)
        self.assertIsNone(revision_item.legacy_id)

    def test_finalized_snapshot_rejects_new_items(self):
        source, source_stage, _ = (
            self._create_finalized_budget_with_item()
        )
        request = self._authenticate(
            self.factory.post(
                (
                    f"/api/budgeting/budget-sheets/{source.pk}/"
                    f"stages/{source_stage.pk}/items/"
                ),
                {
                    "item_type": BudgetSheetItemType.FREE_TEXT,
                    "description_snapshot": "Item indevido",
                    "unit_snapshot": "VB",
                    "quantity": "1.000000",
                    "unit_price": "10.0000",
                },
                format="json",
            )
        )
        view = BudgetSheetViewSet.as_view(
            {"post": "stage_items"}
        )
        response = view(
            request,
            pk=source.pk,
            stage_id=source_stage.pk,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("status", response.data)
        self.assertEqual(source_stage.items.count(), 1)

    def test_revision_can_only_start_from_latest_finalized_revision(self):
        source, _, _ = self._create_finalized_budget_with_item()
        create_view = BudgetSheetViewSet.as_view(
            {"post": "generate_revision"}
        )
        first_request = self._authenticate(
            self.factory.post(
                "/generate-revision/",
                {"reason": "Primeiro ajuste necessário."},
                format="json",
            )
        )
        first_response = create_view(first_request, pk=source.pk)
        self.assertEqual(first_response.status_code, 201)

        second_request = self._authenticate(
            self.factory.post(
                "/generate-revision/",
                {"reason": "Tentativa sobre revisão antiga."},
                format="json",
            )
        )
        second_response = create_view(second_request, pk=source.pk)

        self.assertEqual(second_response.status_code, 400)
        self.assertIn("revision", second_response.data)
        self.assertEqual(BudgetSheet.objects.count(), 2)

    def test_lists_revision_history_in_order(self):
        source, _, _ = self._create_finalized_budget_with_item()
        create_request = self._authenticate(
            self.factory.post(
                "/generate-revision/",
                {"reason": "Atualização de quantitativos."},
                format="json",
            )
        )
        create_view = BudgetSheetViewSet.as_view(
            {"post": "generate_revision"}
        )
        create_view(create_request, pk=source.pk)

        list_request = self._authenticate(
            self.factory.get("/revisions/")
        )
        list_view = BudgetSheetViewSet.as_view(
            {"get": "revisions"}
        )
        response = list_view(list_request, pk=source.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["revision"] for item in response.data],
            [0, 1],
        )
        self.assertTrue(response.data[0]["is_current"])
        self.assertFalse(response.data[1]["is_current"])

    def test_generates_revision_for_sheet_without_proposal(self):
        budget_sheet = BudgetSheet.objects.create(
            party=self.party,
            number="ORC-ADMINISTRATIVO-00",
            revision=0,
        )
        catalog_stage = BudgetStageCatalog.objects.create(
            origin=DataOrigin.HUB,
            name="DESPESAS ADMINISTRATIVAS",
        )
        sheet_stage = BudgetSheetStage.objects.create(
            budget_sheet=budget_sheet,
            stage=catalog_stage,
            order=1,
        )
        BudgetSheetStageItem.objects.create(
            budget_sheet_stage=sheet_stage,
            item_type=BudgetSheetItemType.FREE_TEXT,
            description_snapshot="Taxa administrativa",
            unit_snapshot="VB",
            quantity=Decimal("1.000000"),
            unit_price=Decimal("100.0000"),
            order=1,
        )
        sheet_stage.subtotal = Decimal("100.00")
        sheet_stage.save(update_fields=("subtotal", "updated_at"))
        budget_sheet.total_amount = Decimal("100.00")
        budget_sheet.status = BudgetSheetStatus.FINALIZED
        budget_sheet.save(
            update_fields=("total_amount", "status", "updated_at")
        )

        request = self._authenticate(
            self.factory.post(
                "/generate-revision/",
                {"reason": "Revisão do orçamento administrativo."},
                format="json",
            )
        )
        view = BudgetSheetViewSet.as_view(
            {"post": "generate_revision"}
        )
        response = view(request, pk=budget_sheet.pk)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["number"], "ORC-ADMINISTRATIVO-01")
        self.assertIsNone(response.data["proposal"])

    def test_finalize_requires_an_item_and_locks_the_sheet(self):
        budget_sheet = BudgetSheet.objects.create(
            proposal=self.proposal,
            revision=0,
            number="",
        )
        request = self._authenticate(
            self.factory.post("/finalize/", {}, format="json")
        )
        view = BudgetSheetViewSet.as_view(
            {"post": "finalize"}
        )
        response = view(request, pk=budget_sheet.pk)

        self.assertEqual(response.status_code, 400)
        self.assertIn("stages", response.data)

    def test_finalize_marks_populated_sheet_as_read_only(self):
        budget_sheet, sheet_stage = self._create_budget_sheet_stage()
        BudgetSheetStageItem.objects.create(
            budget_sheet_stage=sheet_stage,
            item_type=BudgetSheetItemType.FREE_TEXT,
            description_snapshot="Serviço inicial",
            unit_snapshot="VB",
            quantity=Decimal("1.000000"),
            unit_price=Decimal("500.0000"),
            order=1,
        )
        request = self._authenticate(
            self.factory.post("/finalize/", {}, format="json")
        )
        view = BudgetSheetViewSet.as_view(
            {"post": "finalize"}
        )
        response = view(request, pk=budget_sheet.pk)

        self.assertEqual(response.status_code, 200)
        budget_sheet.refresh_from_db()
        self.assertEqual(
            budget_sheet.status,
            BudgetSheetStatus.FINALIZED,
        )
        self.assertFalse(response.data["is_editable"])
        self.assertIsNotNone(budget_sheet.finalized_at)

    def test_finalized_snapshot_rejects_nested_updates_and_deletes(self):
        source, source_stage, source_item = (
            self._create_finalized_budget_with_item()
        )

        update_request = self._authenticate(
            self.factory.patch(
                "/item/",
                {"quantity": "3.000000"},
                format="json",
            )
        )
        item_view = BudgetSheetViewSet.as_view(
            {
                "patch": "stage_item_detail",
                "delete": "stage_item_detail",
            }
        )
        update_response = item_view(
            update_request,
            pk=source.pk,
            stage_id=source_stage.pk,
            item_id=source_item.pk,
        )
        self.assertEqual(update_response.status_code, 400)

        delete_item_request = self._authenticate(
            self.factory.delete("/item/")
        )
        delete_item_response = item_view(
            delete_item_request,
            pk=source.pk,
            stage_id=source_stage.pk,
            item_id=source_item.pk,
        )
        self.assertEqual(delete_item_response.status_code, 400)

        delete_stage_request = self._authenticate(
            self.factory.delete("/stage/")
        )
        stage_view = BudgetSheetViewSet.as_view(
            {"delete": "stage_detail"}
        )
        delete_stage_response = stage_view(
            delete_stage_request,
            pk=source.pk,
            stage_id=source_stage.pk,
        )
        self.assertEqual(delete_stage_response.status_code, 400)

        source_item.refresh_from_db()
        self.assertEqual(source_item.quantity, Decimal("2.000000"))
        self.assertTrue(
            BudgetSheetStage.objects.filter(pk=source_stage.pk).exists()
        )

    def test_bdi_application_all_updates_every_composition_and_not_supplies(self):
        budget_sheet, sheet_stage = self._create_budget_sheet_stage()
        first_composition, first_version = self._create_budget_service_composition(
            code="COMP-BDI-ALL-01",
            name="Composição 01",
            total=Decimal("100.0000"),
        )
        second_composition, second_version = self._create_budget_service_composition(
            code="COMP-BDI-ALL-02",
            name="Composição 02",
            total=Decimal("50.0000"),
        )
        first = BudgetSheetStageItem.objects.create(
            budget_sheet_stage=sheet_stage,
            item_type=BudgetSheetItemType.SERVICE_COMPOSITION,
            service_composition=first_composition,
            description_snapshot=first_composition.name,
            unit_snapshot=first_version.unit,
            composition_version_number=first_version.number,
            quantity=Decimal("1.000000"),
            unit_price=Decimal("100.0000"),
            unit_cost=Decimal("100.0000"),
            subtotal=Decimal("100.00"),
            apply_bdi=False,
            order=1,
        )
        second = BudgetSheetStageItem.objects.create(
            budget_sheet_stage=sheet_stage,
            item_type=BudgetSheetItemType.SERVICE_COMPOSITION,
            service_composition=second_composition,
            description_snapshot=second_composition.name,
            unit_snapshot=second_version.unit,
            composition_version_number=second_version.number,
            quantity=Decimal("2.000000"),
            unit_price=Decimal("50.0000"),
            unit_cost=Decimal("50.0000"),
            subtotal=Decimal("100.00"),
            apply_bdi=False,
            order=2,
        )
        supply = BudgetSheetStageItem.objects.create(
            budget_sheet_stage=sheet_stage,
            item_type=BudgetSheetItemType.FREE_TEXT,
            description_snapshot="Insumo avulso",
            unit_snapshot="UN",
            quantity=Decimal("1.000000"),
            unit_price=Decimal("25.0000"),
            subtotal=Decimal("25.00"),
            apply_bdi=False,
            order=3,
        )
        config_response = self._save_bdi_configuration(
            budget_sheet,
            administracao_central="10",
        )
        self.assertEqual(config_response.status_code, 200)

        request = self._authenticate(
            self.factory.put(
                f"/api/budgeting/budget-sheets/{budget_sheet.pk}/bdi-application/",
                {"mode": "ALL"},
                format="json",
            )
        )
        response = BudgetSheetViewSet.as_view({"put": "bdi_application"})(
            request,
            pk=budget_sheet.pk,
        )

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        supply.refresh_from_db()
        self.assertTrue(first.apply_bdi)
        self.assertTrue(second.apply_bdi)
        self.assertFalse(supply.apply_bdi)
        self.assertGreater(first.unit_price, first.unit_cost)
        self.assertGreater(second.unit_price, second.unit_cost)
        self.assertEqual(supply.unit_price, Decimal("25.0000"))

    def test_bdi_application_none_removes_bdi_from_every_composition(self):
        budget_sheet, sheet_stage = self._create_budget_sheet_stage()
        composition, version = self._create_budget_service_composition(
            code="COMP-BDI-NONE",
            name="Composição com BDI",
            total=Decimal("100.0000"),
        )
        item = BudgetSheetStageItem.objects.create(
            budget_sheet_stage=sheet_stage,
            item_type=BudgetSheetItemType.SERVICE_COMPOSITION,
            service_composition=composition,
            description_snapshot=composition.name,
            unit_snapshot=version.unit,
            composition_version_number=version.number,
            quantity=Decimal("1.000000"),
            unit_price=Decimal("100.0000"),
            unit_cost=Decimal("100.0000"),
            subtotal=Decimal("100.00"),
            apply_bdi=False,
            order=1,
        )
        config_response = self._save_bdi_configuration(
            budget_sheet,
            administracao_central="10",
        )
        self.assertEqual(config_response.status_code, 200)

        all_request = self._authenticate(
            self.factory.put(
                f"/api/budgeting/budget-sheets/{budget_sheet.pk}/bdi-application/",
                {"mode": "ALL"},
                format="json",
            )
        )
        all_response = BudgetSheetViewSet.as_view({"put": "bdi_application"})(
            all_request,
            pk=budget_sheet.pk,
        )
        self.assertEqual(all_response.status_code, 200)

        none_request = self._authenticate(
            self.factory.put(
                f"/api/budgeting/budget-sheets/{budget_sheet.pk}/bdi-application/",
                {"mode": "NONE"},
                format="json",
            )
        )
        none_response = BudgetSheetViewSet.as_view({"put": "bdi_application"})(
            none_request,
            pk=budget_sheet.pk,
        )

        self.assertEqual(none_response.status_code, 200)
        item.refresh_from_db()
        self.assertFalse(item.apply_bdi)
        self.assertEqual(item.unit_price, Decimal("100.00"))
        self.assertEqual(item.subtotal, Decimal("100.00"))

    def test_bdi_application_all_requires_configured_bdi_memory(self):
        budget_sheet, sheet_stage = self._create_budget_sheet_stage()
        composition, version = self._create_budget_service_composition(
            code="COMP-BDI-NO-MEMORY",
            name="Composição sem memória",
            total=Decimal("100.0000"),
        )
        BudgetSheetStageItem.objects.create(
            budget_sheet_stage=sheet_stage,
            item_type=BudgetSheetItemType.SERVICE_COMPOSITION,
            service_composition=composition,
            description_snapshot=composition.name,
            unit_snapshot=version.unit,
            composition_version_number=version.number,
            quantity=Decimal("1.000000"),
            unit_price=Decimal("100.0000"),
            unit_cost=Decimal("100.0000"),
            subtotal=Decimal("100.00"),
            apply_bdi=False,
            order=1,
        )

        request = self._authenticate(
            self.factory.put(
                f"/api/budgeting/budget-sheets/{budget_sheet.pk}/bdi-application/",
                {"mode": "ALL"},
                format="json",
            )
        )
        response = BudgetSheetViewSet.as_view({"put": "bdi_application"})(
            request,
            pk=budget_sheet.pk,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("mode", response.data)
