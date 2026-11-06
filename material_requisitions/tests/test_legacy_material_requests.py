from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from django.test import TestCase
from material_requisitions.models import LegacyMaterialRequest, LegacyMaterialRequestItem, LegacyMaterialRequestIssue
from material_requisitions.services.import_legacy_material_requests import MaterialRequestImportError, prepare, persist

class FakeClient:
    def __init__(self, headers, items): self.data = {'requests': headers, 'request-items': items}
    def iter_resource(self, resource, page_size=500): yield from self.data[resource]

def header(pk=1, **kw):
    data={'codRequisicao': pk, 'pcRequisicao': 'PC001', 'reqTipo': 0, 'rmCodigo': 123,
          'status': 'Aprovada', 'reqAprovada': True, 'reprovar': False}
    data.update(kw)
    return data

def item(parent=1, pk=8, **kw):
    data={'requisicaoId': parent, 'codItem': pk, 'quantidade': 2}
    data.update(kw)
    return data

class ImportTests(TestCase):
    def test_preview_and_idempotent_persist(self):
        client=FakeClient([header(), header(2, reqTipo=99, status='Aguardando')], [item(), item(None, 5), item(999, 9)])
        p=prepare(client)
        self.assertEqual(LegacyMaterialRequest.objects.count(), 0)
        for key in ('unknown_type','ambiguous_status','item_without_parent','item_parent_not_found'):
            self.assertEqual(p.counts['issue_'+key], 1)
        persist(p)
        persist(prepare(client))
        self.assertEqual(LegacyMaterialRequest.objects.count(), 2)
        self.assertEqual(LegacyMaterialRequestItem.objects.count(), 1)
        self.assertEqual(LegacyMaterialRequestIssue.objects.count(), 4)
        self.assertEqual(LegacyMaterialRequest.objects.get(legacy_id=1).raw_payload, header())

    def test_changed_payload_updates_existing(self):
        persist(prepare(FakeClient([header()], [item()])))
        persist(prepare(FakeClient([header(pcRequisicao='PC002')], [item(quantidade=5)])))
        self.assertEqual(LegacyMaterialRequest.objects.get().pc, 'PC002')
        self.assertEqual(LegacyMaterialRequestItem.objects.get().raw_payload['quantidade'], 5)

    def test_duplicate_key_aborts(self):
        for client in [FakeClient([header(), header()], []), FakeClient([header()], [item(), item()])]:
            with self.assertRaises(MaterialRequestImportError): prepare(client)
        self.assertEqual(LegacyMaterialRequest.objects.count(), 0)

    def test_atomic_rollback(self):
        with patch.object(LegacyMaterialRequestItem.objects, 'bulk_create', side_effect=RuntimeError('fail')):
            with self.assertRaises(RuntimeError): persist(prepare(FakeClient([header()], [item()])))
        self.assertEqual(LegacyMaterialRequest.objects.count(), 0)

    def test_missing_source_rows_not_deleted(self):
        persist(prepare(FakeClient([header()], [item()])))
        persist(prepare(FakeClient([], [])))
        self.assertEqual(LegacyMaterialRequest.objects.count(), 1)
        self.assertEqual(LegacyMaterialRequestItem.objects.count(), 1)

    def test_command_dry_run(self):
        p=prepare(FakeClient([header()], [item()]))
        with patch('material_requisitions.management.commands.importar_rms_legadas.prepare', return_value=p):
            out=StringIO(); call_command('importar_rms_legadas', stdout=out)
        self.assertIn('SIMULAÇÃO', out.getvalue())
        self.assertEqual(LegacyMaterialRequest.objects.count(), 0)

    def test_connection_failure_leaves_data(self):
        persist(prepare(FakeClient([header()], [item()])))
        class Failing(FakeClient):
            def iter_resource(self, resource, page_size=500):
                if resource == 'request-items': raise RuntimeError('bridge unavailable')
                yield from super().iter_resource(resource, page_size)
        with self.assertRaises(RuntimeError): prepare(Failing([header(2)], []))
        self.assertEqual(list(LegacyMaterialRequest.objects.values_list('legacy_id', flat=True)), [1])
