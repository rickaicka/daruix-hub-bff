"""Verifica a transferência com dados e ContentTypes anteriores à separação."""
import uuid
from datetime import date
from decimal import Decimal
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

OLD = ('budgeting', '0024_materialrequisition_materialrequisitionrevision_and_more')
NEW = ('material_requisitions', '0002_move_content_types')
NAMES = ('MaterialRequisition', 'MaterialRequisitionRevision', 'MaterialRequisitionSection',
         'MaterialRequisitionItem', 'MaterialRequisitionEvent', 'LegacyMaterialRequest',
         'LegacyMaterialRequestItem', 'LegacyMaterialRequestIssue')


class MoveRMTests(TransactionTestCase):
    def test_existing_rows_ids_relations_content_types_and_reverse(self):
        executor = MigrationExecutor(connection)
        executor.migrate([OLD, ('material_requisitions', None)])
        state = executor.loader.project_state([OLD])
        apps = state.apps
        old = {name: apps.get_model('budgeting', name) for name in NAMES}
        User = apps.get_model('accounts', 'User')
        user = User.objects.create(name='Migration', username='migration-rm', email='migration@test.local')
        party = apps.get_model('commercial', 'Party').objects.create(legal_name='Cliente', person_type='COMPANY')
        pc = apps.get_model('commercial', 'Proposal').objects.create(code='PC26990', party=party,
            entry_date=date(2026, 10, 28), work_name='Obra')
        sheet = apps.get_model('budgeting', 'BudgetSheet').objects.create(number='MIG-PO', proposal=pc,
            status='FINALIZED')
        catalog = apps.get_model('budgeting', 'BudgetStageCatalog').objects.create(name='Etapa migração')
        stage = apps.get_model('budgeting', 'BudgetSheetStage').objects.create(budget_sheet=sheet,
            stage=catalog, name_snapshot='Etapa', order=1)
        composition = apps.get_model('budgeting', 'ServiceComposition').objects.create(name='Composição')
        source = apps.get_model('budgeting', 'BudgetSheetStageItem').objects.create(budget_sheet_stage=stage,
            item_type='SERVICE_COMPOSITION', service_composition=composition, description_snapshot='Composição', order=1)
        supply = apps.get_model('budgeting', 'Supply').objects.create(description='Bloco', unit='UN', supply_type='MATERIAL')
        root = old['MaterialRequisition'].objects.create(proposal=pc, sequence=1, number='RM-MIG-001',
            requester=user, creation_key=uuid.uuid4(), creation_hash='a'*64)
        revision = old['MaterialRequisitionRevision'].objects.create(requisition=root, budget_sheet=sheet,
            owner=user, reference_date=date(2026, 10, 28), status=1, version=7,
            source_snapshot={'pc': pc.code, 'preservado': True})
        root.current_revision=revision;root.approved_revision=revision;root.save()
        section=old['MaterialRequisitionSection'].objects.create(revision=revision,
            source_stage=stage, source_composition=source, stage_name='Etapa', description='Composição', position=1)
        item=old['MaterialRequisitionItem'].objects.create(section=section, supply=supply,
            description='Bloco', unit='UN', supply_type='MATERIAL', quantity=Decimal('2.123456'), position=1)
        event=old['MaterialRequisitionEvent'].objects.create(revision=revision, actor=user, action='APPROVE', version=7)
        legacy=old['LegacyMaterialRequest'].objects.create(legacy_id=9001, legacy_type=0,
            raw_payload={'reqTipo': None}, payload_hash='b'*64, imported_at=timezone.now())
        legacy_item=old['LegacyMaterialRequestItem'].objects.create(request=legacy, legacy_item_id=1,
            raw_payload={'quantidade': 5}, payload_hash='c'*64, imported_at=timezone.now())
        issue=old['LegacyMaterialRequestIssue'].objects.create(identity='d'*64, reason='ambiguous_status',
            raw_payload={'status': 'Aguardando'}, imported_at=timezone.now())
        rows = dict(zip(NAMES, (root, revision, section, item, event, legacy, legacy_item, issue)))
        ContentType=apps.get_model('contenttypes','ContentType')
        # Em execução do teste o post_migrate pode já ter criado o tipo do app novo.
        ContentType.objects.filter(app_label='material_requisitions', model__in=[n.lower() for n in NAMES]).delete()
        ct,_=ContentType.objects.get_or_create(app_label='budgeting',model='materialrequisition')
        Permission=apps.get_model('auth','Permission')
        permission,_=Permission.objects.get_or_create(content_type=ct,codename='view_materialrequisition',defaults={'name':'Ver RM'})
        permission_id, ct_id=permission.pk,ct.pk
        user.user_permissions.add(permission)
        try:
            executor=MigrationExecutor(connection);executor.migrate([NEW])
            new_apps=executor.loader.project_state([NEW]).apps
            for name,obj in rows.items():
                self.assertEqual(new_apps.get_model('material_requisitions',name).objects.get(pk=obj.pk).pk,obj.pk)
            new_root=new_apps.get_model('material_requisitions','MaterialRequisition').objects.get(pk=root.pk)
            self.assertEqual(new_root.approved_revision_id,revision.pk)
            self.assertEqual(new_root.current_revision_id,revision.pk)
            new_rev=new_root.current_revision
            self.assertEqual(new_rev.version,7)
            self.assertEqual(new_rev.source_snapshot,{'pc':pc.code,'preservado':True})
            self.assertEqual(new_rev.sections.get().items.get().quantity,Decimal('2.123456'))
            self.assertEqual(new_apps.get_model('auth','Permission').objects.get(pk=permission_id).content_type_id,ct_id)
            self.assertEqual(new_apps.get_model('contenttypes','ContentType').objects.get(pk=ct_id).app_label,'material_requisitions')
            self.assertTrue(new_apps.get_model('accounts','User').objects.get(pk=user.pk).user_permissions.filter(pk=permission_id).exists())
            self.assertNotIn(('budgeting','materialrequisition'),executor.loader.project_state([NEW]).models)
            # Reversão é somente estado/ContentTypes; os dados continuam nas mesmas tabelas.
            executor=MigrationExecutor(connection);executor.migrate([OLD,('material_requisitions',None)])
            back=executor.loader.project_state([OLD]).apps
            self.assertEqual(back.get_model('budgeting','MaterialRequisitionRevision').objects.get(pk=revision.pk).version,7)
            self.assertEqual(back.get_model('contenttypes','ContentType').objects.get(pk=ct_id).app_label,'budgeting')
        finally:
            executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())
