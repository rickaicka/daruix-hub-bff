from unittest.mock import Mock

from django.test import TestCase

from budgeting.choices import (
    BudgetStageLegacySource,
    CompositionStatus,
    DataOrigin,
    SupplyType,
)

from budgeting.models import (
    BudgetStageCatalog,
    MaterialGroup,
    ServiceComposition,
    ServiceCompositionItem,
    Supply,
)
from budgeting.services.import_legacy import LegacyCatalogImporter


class LegacyCatalogImporterTests(TestCase):
    def test_uses_readable_database_table_names(self):
        self.assertEqual(Supply._meta.db_table, "budgeting_supply")
        self.assertEqual(
            ServiceComposition._meta.db_table,
            "budgeting_service_composition",
        )

    def test_imports_real_supply_contract_idempotently(self):
        row = {
            "insumoCodigo": 1,
            "insumoDescricao": "Cimento Portland",
            "insumoUnidade": "KG",
            "insumoFiltro": 1,
            "insumoTipo": 0,
            "insumoEspecificacaoComplementar": "CP II",
        }
        client = Mock()
        client.iter_resource.side_effect = lambda resource: iter([row])
        importer = LegacyCatalogImporter(client)

        first = importer.import_supplies()
        imported_at = Supply.objects.get().imported_at
        second = importer.import_supplies()

        self.assertEqual(Supply.objects.count(), 1)
        supply = Supply.objects.get()
        self.assertEqual(first.created, 1)
        self.assertEqual(second.unchanged, 1)
        self.assertEqual(supply.imported_at, imported_at)
        self.assertEqual(supply.origin, DataOrigin.LEGACY)
        self.assertEqual(supply.legacy_id, 1)
        self.assertEqual(supply.description, "Cimento Portland")
        self.assertEqual(supply.unit, "KG")
        self.assertEqual(supply.specification, "CP II")
        self.assertEqual(supply.supply_type, SupplyType.MATERIAL)
        self.assertTrue(supply.is_active)

    def test_imports_distinct_group_names_with_repeated_legacy_id(self):
        rows = [
            {
                "grupoDeMaterialID": 1,
                "grupoDeMaterialNome": "Material Hidráulico",
            },
            {
                "grupoDeMaterialID": 1,
                "grupoDeMaterialNome": "Material Elétrico",
            },
        ]
        client = Mock()
        client.iter_resource.return_value = iter(rows)

        counters = LegacyCatalogImporter(client).import_material_groups()

        self.assertEqual(counters.created, 2)
        self.assertEqual(MaterialGroup.objects.count(), 2)
        self.assertEqual(
            set(MaterialGroup.objects.values_list("nome", flat=True)),
            {"Material Hidráulico", "Material Elétrico"},
        )

    def test_supply_dry_run_reports_creation_without_persisting(self):
        client = Mock()
        client.iter_resource.return_value = iter(
            [{"insumoCodigo": 10, "insumoDescricao": "Areia"}]
        )

        counters = LegacyCatalogImporter(client).import_supplies(dry_run=True)

        self.assertEqual(counters.read, 1)
        self.assertEqual(counters.created, 1)
        self.assertEqual(counters.skipped, 0)
        self.assertEqual(Supply.objects.count(), 0)

    def test_reports_import_progress(self):
        client = Mock()
        client.iter_resource.return_value = iter(
            [{"insumoCodigo": 10, "insumoDescricao": "Areia"}]
        )
        progress = Mock()

        LegacyCatalogImporter(
            client,
            progress_callback=progress,
        ).import_supplies(dry_run=True)

        progress.assert_called_once()
        resource, counters = progress.call_args.args
        self.assertEqual(resource, "supplies")
        self.assertEqual(counters.read, 1)

    def test_imports_real_composition_contract_without_fake_items(self):
        client = Mock()
        client.iter_resource.return_value = iter(
            [
                {
                    "composicaoDeServicoId": 22,
                    "codigoParaVincular": "1001001",
                    "composicaoDeServicoNome": "Limpeza mecanizada geral",
                    "composicaoDeServicoUnidadeDeMedida": "M²",
                    "composicaoDeServicoValor": "331.1000",
                }
            ]
        )

        counters = LegacyCatalogImporter(client).import_compositions()

        composition = ServiceComposition.objects.get()
        version = composition.versions.get()
        self.assertEqual(counters.created, 1)
        self.assertEqual(composition.legacy_id, 22)
        self.assertEqual(composition.code, "1001001")
        self.assertEqual(version.status, CompositionStatus.HISTORICAL)
        self.assertEqual(version.origin, DataOrigin.LEGACY)
        self.assertEqual(version.unit, "M²")
        self.assertEqual(str(version.total), "331.1000")
        self.assertFalse(version.items.exists())

    def test_repairs_old_mapping_even_when_payload_hash_is_unchanged(self):
        row = {
            "composicaoDeServicoId": 22,
            "codigoParaVincular": "1001001",
            "composicaoDeServicoNome": "Limpeza mecanizada geral",
            "composicaoDeServicoUnidadeDeMedida": "M²",
            "composicaoDeServicoValor": "331.1000",
        }
        client = Mock()
        client.iter_resource.side_effect = lambda resource: iter([row])
        importer = LegacyCatalogImporter(client)
        importer.import_compositions()

        composition = ServiceComposition.objects.get()
        composition.code = ""
        composition.save(update_fields=("code", "updated_at"))
        version = composition.versions.get(number=1)
        version.unit = ""
        version.save(update_fields=("unit", "updated_at"))

        counters = importer.import_compositions()

        composition.refresh_from_db()
        version.refresh_from_db()
        self.assertEqual(counters.updated, 1)
        self.assertEqual(composition.code, "1001001")
        self.assertEqual(version.unit, "M²")

    def test_imports_composition_items_idempotently(self):
        supply = Supply.objects.create(
            origin=DataOrigin.LEGACY,
            legacy_table="tblInsumos",
            legacy_id=1,
            description="SERVENTE (SGSP)",
            unit="H",
            supply_type=SupplyType.LABOR,
        )
        composition = ServiceComposition.objects.create(
            origin=DataOrigin.LEGACY,
            legacy_table="tblComposicaoDeServico",
            legacy_id=22,
            code="1001001",
            name="Limpeza mecanizada geral",
        )
        version = composition.versions.create(
            number=1,
            status=CompositionStatus.HISTORICAL,
            origin=DataOrigin.LEGACY,
            unit="M²",
        )
        row = {
            "itemComposicaoDeServicoId": 1,
            "itemComposicaoDeServicoCodigoParaVincular": "1001001",
            "itemComposicaoDeServicoInsumo": "SERVENTE (SGSP)",
            "itemComposicaoDeServicoUnidade": "H",
            "itemComposicaoDeServicoComplemento": None,
            "itemComposicaoDeServicoQtde": 1.0,
            "itemComposicaoDeServicoValor": "24.1000",
            "composicaoDeServicoId": 22,
            "itemComposicaoDeServicoValorMAT": "0.0000",
            "itemComposicaoDeServicoComposto": 0,
        }
        client = Mock()
        client.iter_resource.side_effect = lambda resource: iter([row])
        importer = LegacyCatalogImporter(client)

        first = importer.import_composition_items()
        second = importer.import_composition_items()

        self.assertEqual(first.created, 1)
        self.assertEqual(second.unchanged, 1)
        self.assertEqual(ServiceCompositionItem.objects.count(), 1)
        item = ServiceCompositionItem.objects.get()
        self.assertEqual(item.version, version)
        self.assertEqual(item.supply, supply)
        self.assertEqual(item.legacy_id, 1)
        self.assertEqual(str(item.coefficient), "1.000000")
        self.assertEqual(str(item.labor_unit_price), "24.1000")
        self.assertEqual(str(item.material_unit_price), "0.0000")

    def test_preserves_unmatched_composition_item_as_free_text(self):
        composition = ServiceComposition.objects.create(
            origin=DataOrigin.LEGACY,
            legacy_table="tblComposicaoDeServico",
            legacy_id=22,
            code="1001001",
            name="Limpeza mecanizada geral",
        )
        composition.versions.create(
            number=1,
            status=CompositionStatus.HISTORICAL,
            origin=DataOrigin.LEGACY,
            unit="M²",
        )
        client = Mock()
        client.iter_resource.return_value = iter(
            [
                {
                    "itemComposicaoDeServicoId": 99,
                    "itemComposicaoDeServicoInsumo": "ITEM NÃO CADASTRADO",
                    "itemComposicaoDeServicoUnidade": "UN",
                    "itemComposicaoDeServicoQtde": 2,
                    "itemComposicaoDeServicoValor": "10.0000",
                    "itemComposicaoDeServicoValorMAT": "4.0000",
                    "itemComposicaoDeServicoComposto": 0,
                    "composicaoDeServicoId": 22,
                }
            ]
        )

        counters = LegacyCatalogImporter(client).import_composition_items()

        self.assertEqual(counters.created, 1)
        item = ServiceCompositionItem.objects.get()
        self.assertEqual(item.item_type, "FREE_TEXT")
        self.assertIsNone(item.supply)
        self.assertIsNone(item.subcomposition)
        self.assertEqual(str(item.material_unit_price), "4.0000")
        self.assertEqual(str(item.labor_unit_price), "6.0000")

    def test_imports_stage_catalog_idempotently(self):
        row = {
            "legacy_id": 1,
            "legacy_key": "a" * 64,
            "legacy_source": "WORK_COST_CENTER",
            "code": "CC.01",
            "name": "CANTEIRO DE OBRAS",
            "category": "OPERATIONAL",
            "is_active": True,
            "legacy_payload": {
                "table_name": "tblCentroDeCustoObra",
            },
        }

        client = Mock()
        client.list_stage_catalog.return_value = [row]

        importer = LegacyCatalogImporter(client)

        first = importer.import_stage_catalog()
        imported_at = BudgetStageCatalog.objects.get().imported_at
        second = importer.import_stage_catalog()

        self.assertEqual(first.created, 1)
        self.assertEqual(second.unchanged, 1)
        self.assertEqual(
            BudgetStageCatalog.objects.count(),
            1,
        )

        stage = BudgetStageCatalog.objects.get()

        self.assertEqual(
            stage.origin,
            DataOrigin.LEGACY,
        )
        self.assertEqual(
            stage.legacy_source,
            BudgetStageLegacySource.WORK_COST_CENTER,
        )
        self.assertEqual(stage.legacy_id, 1)
        self.assertEqual(stage.code, "CC.01")
        self.assertEqual(stage.name, "CANTEIRO DE OBRAS")
        self.assertEqual(
            stage.legacy_category,
            "OPERATIONAL",
        )
        self.assertTrue(stage.is_active)
        self.assertEqual(stage.imported_at, imported_at)

    def test_stage_catalog_preserves_equal_ids_from_different_sources(self):
        client = Mock()
        client.list_stage_catalog.return_value = [
            {
                "legacy_id": 1,
                "legacy_key": "a" * 64,
                "legacy_source": "WORK_COST_CENTER",
                "code": "CC.01",
                "name": "CANTEIRO DE OBRAS",
                "category": "OPERATIONAL",
                "is_active": True,
                "legacy_payload": {},
            },
            {
                "legacy_id": 1,
                "legacy_key": "b" * 64,
                "legacy_source": "ADMINISTRATIVE_COST_CENTER",
                "code": None,
                "name": "ADMINISTRAÇÃO",
                "category": "ADMINISTRATIVE",
                "is_active": True,
                "legacy_payload": {},
            },
        ]

        counters = LegacyCatalogImporter(
            client
        ).import_stage_catalog()

        self.assertEqual(counters.created, 2)
        self.assertEqual(
            BudgetStageCatalog.objects.count(),
            2,
        )

    def test_stage_catalog_deactivates_only_missing_legacy_stages(self):
        kept = BudgetStageCatalog.objects.create(
            origin=DataOrigin.LEGACY,
            legacy_source=(
                BudgetStageLegacySource.WORK_COST_CENTER
            ),
            legacy_id=1,
            legacy_key="a" * 64,
            code="CC.01",
            name="CANTEIRO DE OBRAS",
            legacy_category="OPERATIONAL",
        )
        missing = BudgetStageCatalog.objects.create(
            origin=DataOrigin.LEGACY,
            legacy_source=(
                BudgetStageLegacySource.WORK_COST_CENTER
            ),
            legacy_id=2,
            legacy_key="b" * 64,
            code="CC.02",
            name="DESPESAS DE CANTEIRO",
            legacy_category="OPERATIONAL",
        )
        hub_stage = BudgetStageCatalog.objects.create(
            origin=DataOrigin.HUB,
            name="ETAPA CRIADA NO HUB",
        )

        client = Mock()
        client.list_stage_catalog.return_value = [
            {
                "legacy_id": 1,
                "legacy_key": "a" * 64,
                "legacy_source": "WORK_COST_CENTER",
                "code": "CC.01",
                "name": "CANTEIRO DE OBRAS",
                "category": "OPERATIONAL",
                "is_active": True,
                "legacy_payload": {},
            }
        ]

        counters = LegacyCatalogImporter(
            client
        ).import_stage_catalog()

        kept.refresh_from_db()
        missing.refresh_from_db()
        hub_stage.refresh_from_db()

        self.assertEqual(counters.deactivated, 1)
        self.assertTrue(kept.is_active)
        self.assertFalse(missing.is_active)
        self.assertTrue(hub_stage.is_active)

    def test_stage_catalog_dry_run_does_not_persist(self):
        client = Mock()
        client.list_stage_catalog.return_value = [
            {
                "legacy_id": 1,
                "legacy_key": "a" * 64,
                "legacy_source": "WORK_COST_CENTER",
                "code": "CC.01",
                "name": "CANTEIRO DE OBRAS",
                "category": "OPERATIONAL",
                "is_active": True,
                "legacy_payload": {},
            }
        ]

        counters = LegacyCatalogImporter(
            client
        ).import_stage_catalog(
            dry_run=True,
        )

        self.assertEqual(counters.created, 1)
        self.assertEqual(
            BudgetStageCatalog.objects.count(),
            0,
        )