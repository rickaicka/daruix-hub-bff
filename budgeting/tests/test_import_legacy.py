from unittest.mock import Mock

from django.test import TestCase

from budgeting.choices import CompositionStatus, DataOrigin, SupplyType
from budgeting.models import ServiceComposition, Supply
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
        self.assertEqual(supply.code, "1")
        self.assertEqual(supply.description, "Cimento Portland")
        self.assertEqual(supply.unit, "KG")
        self.assertEqual(supply.specification, "CP II")
        self.assertEqual(supply.supply_type, SupplyType.OTHER)
        self.assertTrue(supply.is_active)

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
