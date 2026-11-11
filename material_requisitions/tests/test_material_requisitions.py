import uuid
from copy import deepcopy
from datetime import date
from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from accounts.models import User, UserGroup, Permission, GroupPermission
from commercial.models import Party, Proposal
from budgeting.models import (BudgetSheet, BudgetSheetStage, BudgetSheetStageItem,
                              BudgetStageCatalog, Supply)
from material_requisitions.models import MaterialRequisition, MaterialRequisitionRevision, MaterialRequisitionEvent
from budgeting.services.compositions import create_composition
from budgeting.services.budget_sheets import build_composition_snapshot


class OperationalRMTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(name='Owner', username='rmowner', email='rmowner@test.local')
        self.other = User.objects.create_user(name='Other', username='rmother', email='rmother@test.local')
        group = UserGroup.objects.create(name='Diretoria', user_type='COLABORADOR')
        self.director = User.objects.create_user(name='Director', username='rmdirector', email='dir@test.local', group=group)
        permission, _ = Permission.objects.get_or_create(code='material_requisition.approve', defaults={'module': 'material_requisitions', 'description': 'Aprovação RM'})
        GroupPermission.objects.get_or_create(group=group, permission=permission)
        self.party = Party.objects.create(legal_name='Cliente Teste', person_type='COMPANY')
        self.proposal = Proposal.objects.create(code='PC26001', party=self.party,
            entry_date=date(2026, 10, 28), work_name='Obra', technical_responsible=self.director)
        self.supply = Supply.objects.create(description='Bloco', supply_type='MATERIAL', unit='UN')
        self.service = Supply.objects.create(description='Serviço', supply_type='SERVICE', unit='H')
        self.comp = create_composition({'name': 'Composição', 'unit': 'VB', 'items': [
            {'item_type': 'SUPPLY', 'supply': self.supply, 'coefficient': Decimal('2'),
             'material_unit_price': Decimal('1'), 'labor_unit_price': Decimal('0'),
             'equipment_unit_price': Decimal('0')},
            {'item_type': 'SUPPLY', 'supply': self.service, 'coefficient': Decimal('3'),
             'material_unit_price': Decimal('0'), 'labor_unit_price': Decimal('1'),
             'equipment_unit_price': Decimal('0')}]})
        self.sheet = BudgetSheet.objects.create(number='BUD-1', proposal=self.proposal)
        self.stage = BudgetSheetStage.objects.create(budget_sheet=self.sheet,
            stage=BudgetStageCatalog.objects.create(name='Etapa A'), order=1)
        snap = build_composition_snapshot(self.comp)
        self.source = BudgetSheetStageItem.objects.create(budget_sheet_stage=self.stage,
            service_composition=self.comp, item_type='SERVICE_COMPOSITION',
            description_snapshot='Composição', unit_snapshot='VB', quantity=Decimal('1'),
            unit_cost=Decimal(snap['total']), unit_price=Decimal(snap['total']),
            composition_snapshot=snap, composition_version_number=snap['version_number'], order=1)
        BudgetSheet.objects.filter(pk=self.sheet.pk).update(status='FINALIZED')
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.base = '/api/material-requisitions/'

    def create(self, **changes):
        data = {'proposal': self.proposal.pk, 'creation_key': str(uuid.uuid4()),
                'reference_date': '2026-10-28', 'request_type': 0}
        data.update(changes)
        response = self.client.post(self.base, data, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data, data

    def post(self, rev, action, extra=None, expected=200):
        data = {'expected_version': rev['version'], **(extra or {})}
        response = self.client.post(f"{self.base}{rev['id']}/{action}/", data, format='json')
        self.assertEqual(response.status_code, expected, response.data)
        return response.data

    def ready(self):
        rev, _ = self.create()
        rev = self.post(rev, 'sections', {'source_stage': self.stage.pk, 'description': 'Descrição geral livre'})
        return self.post(rev, f"sections/{rev['sections'][0]['id']}/items", {'supply': self.supply.pk, 'quantity': '2'})

    def test_only_technical_responsible_with_permission_and_not_creator_can_approve(self):
        from material_requisitions.services.requisitions import can_decide_rm
        rev = self.post(self.ready(), 'submit')
        instance = MaterialRequisitionRevision.objects.select_related('requisition', 'budget_sheet__proposal').get(pk=rev['id'])
        self.assertFalse(can_decide_rm(instance, self.owner))
        self.assertFalse(can_decide_rm(instance, self.other))
        self.assertTrue(can_decide_rm(instance, self.director))
        self.client.force_authenticate(self.owner)
        self.post(rev, 'approve', expected=403)
        # Mesmo que o criador seja nomeado responsável técnico, não pode aprovar.
        self.proposal.technical_responsible = self.owner
        self.proposal.save(update_fields=['technical_responsible'])
        self.assertFalse(can_decide_rm(instance, self.owner))
        self.client.force_authenticate(self.director)
        self.post(rev, 'approve')

    def test_directoria_with_permission_can_approve_without_being_technical_responsible(self):
        from material_requisitions.services.requisitions import can_decide_rm
        rev = self.post(self.ready(), 'submit')
        technical_group = UserGroup.objects.create(name='Engenharia', user_type='COLABORADOR')
        technical = User.objects.create_user(name='RT', username='rmtech', email='rt@test.local', group=technical_group)
        self.proposal.technical_responsible = technical
        self.proposal.save(update_fields=['technical_responsible'])
        instance = MaterialRequisitionRevision.objects.select_related('requisition__proposal').get(pk=rev['id'])
        self.assertTrue(can_decide_rm(instance, self.director))
        self.client.force_authenticate(self.director)
        response = self.client.get(f"{self.base}{rev['id']}/")
        self.assertTrue(response.data['allowed_actions']['approve'])
        self.post(rev, 'approve')

    def test_approve_and_reject_have_identical_visibility_for_eligible_director(self):
        rev = self.post(self.ready(), 'submit')
        self.client.force_authenticate(self.director)
        response = self.client.get(f"{self.base}{rev['id']}/")
        self.assertEqual(response.status_code, 200)
        actions = response.data['allowed_actions']
        self.assertTrue(actions['approve'])
        self.assertTrue(actions['reject'])
        rejected = self.post(rev, 'reject', {'reason': 'Dados incorretos'})
        self.assertEqual(rejected['status'], 0)
        self.assertFalse(rejected['allowed_actions']['approve'])
        self.assertFalse(rejected['allowed_actions']['reject'])

    def test_approve_and_reject_hidden_for_request_creator_and_unprivileged(self):
        rev = self.post(self.ready(), 'submit')
        for user in (self.owner, self.other):
            self.client.force_authenticate(user)
            response = self.client.get(f"{self.base}{rev['id']}/")
            self.assertFalse(response.data['allowed_actions']['approve'])
            self.assertFalse(response.data['allowed_actions']['reject'])

    def test_submit_notifies_eligible_director_and_reject_resolves_pending(self):
        from unittest.mock import patch
        from material_requisitions.services.notifications import _deliver
        from accounts.models import HubNotification
        rev = self.post(self.ready(), 'submit')
        # Os eventos transacionais são executados explicitamente para testar
        # os mesmos efeitos que ocorreriam após commit no ambiente real.
        with patch('material_requisitions.services.notifications.publish') as publish:
            _deliver(rev['id'], self.owner.pk, 'submit')
            recipients = publish.call_args.kwargs['recipients']
            self.assertIn(self.director.pk, [u.pk for u in recipients])
            self.assertNotIn(self.owner.pk, [u.pk for u in recipients])
            self.assertEqual(publish.call_args.kwargs['message'], rev['number'])
        self.client.force_authenticate(self.director)
        with patch('material_requisitions.services.notifications.resolve') as resolve:
            _deliver(rev['id'], self.director.pk, 'reject')
            self.assertEqual(resolve.call_args.kwargs['resource_id'], rev['requisition'])
            self.assertEqual(resolve.call_args.kwargs['event'], 'rm.submitted')

    def test_technical_responsible_needs_explicit_permission(self):
        from material_requisitions.services.requisitions import can_decide_rm
        rev = self.post(self.ready(), 'submit')
        technical_group = UserGroup.objects.create(name='Engenharia', user_type='COLABORADOR')
        technical = User.objects.create_user(name='RT', username='rmtech', email='rt@test.local', group=technical_group)
        self.proposal.technical_responsible = technical
        self.proposal.save(update_fields=['technical_responsible'])
        instance = MaterialRequisitionRevision.objects.select_related('requisition__proposal').get(pk=rev['id'])
        self.assertFalse(can_decide_rm(instance, technical))
        self.client.force_authenticate(technical)
        self.post(rev, 'approve', expected=403)
        permission = Permission.objects.get(code='material_requisition.approve')
        GroupPermission.objects.create(group=technical_group, permission=permission)
        self.assertTrue(can_decide_rm(instance, technical))
        self.post(rev, 'approve')

    def test_director_cannot_approve_own_request(self):
        from material_requisitions.services.requisitions import can_decide_rm
        self.client.force_authenticate(self.director)
        rev = self.post(self.ready(), 'submit')
        instance = MaterialRequisitionRevision.objects.select_related('requisition__proposal').get(pk=rev['id'])
        self.assertFalse(can_decide_rm(instance, self.director))
        self.post(rev, 'approve', expected=403)

    def test_creation_identity_and_frozen_origin(self):
        rev, data = self.create()
        again = self.client.post(self.base, data, format='json')
        self.assertEqual(again.data['id'], rev['id'])
        self.assertEqual(MaterialRequisition.objects.count(), 1)
        self.assertEqual(rev['revision'], 0)
        self.assertEqual(rev['status'], 3)
        self.assertEqual(rev['source_snapshot']['client'], 'Cliente Teste')
        changed = dict(data, notes='different')
        self.assertEqual(self.client.post(self.base, changed, format='json').status_code, 409)

    def test_waiting_creator_only_and_decision_conflict(self):
        rev = self.post(self.ready(), 'submit')
        self.client.force_authenticate(self.director)
        url = f"{self.base}{rev['id']}/"
        self.assertEqual(self.client.patch(url, {'expected_version': rev['version'], 'notes': 'X'}, format='json').status_code, 403)
        self.client.force_authenticate(self.owner)
        updated = self.client.patch(url, {'expected_version': rev['version'], 'notes': 'New'}, format='json')
        self.assertEqual(updated.status_code, 200, updated.data)
        self.client.force_authenticate(self.director)
        self.post(rev, 'approve', expected=409)
        approved = self.post(updated.data, 'approve')
        self.assertEqual(approved['status'], 1)

    def test_approved_rm_preserves_snapshot_and_disallows_revisions(self):
        rev = self.post(self.ready(), 'submit')
        self.client.force_authenticate(self.director)
        approved = self.post(rev, 'approve')
        original_snapshot = deepcopy(approved['sections'][0]['composition_snapshot'])
        self.post(approved, 'generate-revision', {'reason': 'Alteração'}, expected=400)
        self.assertEqual(MaterialRequisitionRevision.objects.filter(requisition_id=approved['requisition']).count(), 1)
        self.assertEqual(self.client.get(f"{self.base}{approved['id']}/").data['sections'][0]['composition_snapshot'], original_snapshot)
        self.assertEqual(self.client.patch(f"{self.base}{approved['id']}/", {
            'expected_version': approved['version'], 'notes': 'Alteração indevida'
        }, format='json').status_code, 403)

    def test_cancel_terminal_and_number_never_reused(self):
        rev, _ = self.create()
        cancelled = self.post(rev, 'cancel', {'reason': 'Cancelamento'})
        self.assertEqual(cancelled['status'], 2)
        self.assertIsNone(cancelled['approved_revision'])
        self.post(cancelled, 'generate-revision', {'reason': 'Reuso'}, expected=400)
        self.assertEqual(self.client.get(self.base).data['count'], 0)
        next_rev, _ = self.create()
        self.assertNotEqual(rev['number'], next_rev['number'])

    def test_invalid_cross_context_rejected_without_mutation(self):
        rev, _ = self.create()
        foreign = BudgetSheet.objects.create(number='OTHER', proposal=self.proposal)
        foreign_stage = BudgetSheetStage.objects.create(budget_sheet=foreign,
            stage=self.stage.stage, order=1)
        other = BudgetSheetStageItem.objects.create(budget_sheet_stage=foreign_stage,
            service_composition=self.comp, item_type='SERVICE_COMPOSITION',
            description_snapshot='Other', unit_snapshot='VB', quantity=1,
            composition_snapshot=self.source.composition_snapshot, order=1)
        self.post(rev, 'sections', {'source_stage': foreign_stage.pk, 'description': 'Outra descrição'}, expected=404)
        self.assertEqual(MaterialRequisitionRevision.objects.get(pk=rev['id']).version, 1)
        self.post(rev, 'submit', expected=400)

    def test_strict_payload_and_item_type(self):
        rev, _ = self.create()
        response = self.client.patch(f"{self.base}{rev['id']}/", {'expected_version': rev['version'], 'status': 1}, format='json')
        self.assertEqual(response.status_code, 400)
        rev = self.post(rev, 'sections', {'source_stage': self.stage.pk, 'description': 'Descrição geral livre'})
        self.post(rev, f"sections/{rev['sections'][0]['id']}/items", {'supply': self.service.pk, 'quantity': '1'}, expected=400)
        self.post(rev, f"sections/{rev['sections'][0]['id']}/items", {'supply': self.supply.pk, 'quantity': '-1'}, expected=400)

    def test_load_composition_filters_and_freezes(self):
        rev, _ = self.create()
        rev = self.post(rev, 'sections', {'source_stage': self.stage.pk, 'description': 'Descrição geral livre'})
        original = deepcopy(self.source.composition_snapshot)
        path = f"sections/{rev['sections'][0]['id']}/load-composition"
        self.post(rev, path, {'multiplier': '1.5'}, expected=400)
        result = self.post(rev, path, {'multiplier': '1'})
        self.assertEqual(result['composition_load_report']['added'], 1)
        self.assertEqual(len(result['composition_load_report']['skipped']), 1)
        self.assertEqual(Decimal(result['sections'][0]['items'][0]['quantity']), Decimal('2'))
        self.source.refresh_from_db()
        self.assertEqual(self.source.composition_snapshot, original)

    def test_recalculate_po_items_keeps_ids_and_uses_original_coefficients(self):
        rev, _ = self.create()
        rev = self.post(rev, 'sections', {'source_stage': self.stage.pk, 'description': 'Teste'})
        path = f"sections/{rev['sections'][0]['id']}/load-composition"
        first = self.post(rev, path, {'multiplier': '1'})
        original = first['sections'][0]['items'][0]
        self.assertEqual(Decimal(original['quantity']), Decimal('2'))
        self.post(first, path, {'multiplier': '2'}, expected=409)
        self.post(first, path, {'multiplier': '2', 'recalculate': True}, expected=400)
        second = self.post(first, path, {'multiplier': '0.5', 'recalculate': True})
        updated = second['sections'][0]['items'][0]
        self.assertEqual(updated['id'], original['id'])
        self.assertEqual(Decimal(updated['quantity']), Decimal('1'))
        self.assertEqual(second['composition_load_report']['updated'], 1)
        self.assertEqual(second['composition_load_report']['added'], 0)
        third = self.post(second, path, {'multiplier': '1', 'recalculate': True})
        self.assertEqual(Decimal(third['sections'][0]['items'][0]['quantity']), Decimal('2'))
        self.assertEqual(len(third['sections'][0]['items']), 1)
        events = MaterialRequisitionEvent.objects.filter(revision_id=third['id'], action='RECALCULATE_COMPOSITION')
        self.assertEqual(events.count(), 2)
        self.assertEqual(events.first().payload['changes'][0]['before'], '2.000000')
        self.assertEqual(events.first().payload['changes'][0]['after'], '1.000000')

    def test_recalculate_does_not_touch_items_without_po_origin(self):
        rev, _ = self.create()
        rev = self.post(rev, 'sections', {'source_stage': self.stage.pk, 'description': 'Teste'})
        section_id = rev['sections'][0]['id']
        rev = self.post(rev, f'sections/{section_id}/load-composition', {'multiplier': '1'})
        # Itens manuais são identificados por source_path vazio e não devem ser alterados.
        from material_requisitions.models import MaterialRequisitionItem
        section = MaterialRequisitionRevision.objects.get(pk=rev['id']).sections.get(pk=section_id)
        manual = MaterialRequisitionItem.objects.create(section=section, supply=self.supply,
            supply_type='MATERIAL', description='Item manual', unit='UN',
            quantity=Decimal('7'), position=2, source_path='')
        recalculated = self.post(rev, f'sections/{section_id}/load-composition',
                                 {'multiplier': '0.5', 'recalculate': True})
        manual.refresh_from_db()
        self.assertEqual(manual.quantity, Decimal('7'))
        self.assertEqual(len(recalculated['sections'][0]['items']), 2)

    def test_authenticated_employee_only(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.base).status_code, 401)
        self.other.user_type = 'FORNECEDOR'
        self.other.save(update_fields=['user_type'])
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.base).status_code, 403)

    def test_rejection_reason_and_new_rm(self):
        rev = self.post(self.ready(), 'submit')
        self.client.force_authenticate(self.other)
        self.post(rev, 'approve', expected=403)
        self.client.force_authenticate(self.director)
        self.post(rev, 'reject', expected=400)
        rejected = self.post(rev, 'reject', {'reason': 'Corrigir'})
        self.assertEqual(rejected['status'], 0)
        self.assertTrue(MaterialRequisitionEvent.objects.filter(revision_id=rejected['id'], action='REJECT').exists())
        self.client.force_authenticate(self.owner)
        self.post(rejected, 'generate-revision', {'reason': 'Correção'}, expected=400)
        fresh, _ = self.create()
        self.assertNotEqual(fresh['number'], rejected['number'])
        self.assertEqual(fresh['status'], 3)

    def test_context_stage_restriction_and_draft_sheet(self):
        self.assertEqual(self.client.get(self.base + f'context/?proposal={self.proposal.pk}').data['count'], 1)
        result = self.client.get(self.base + f'context/?budget_sheet={self.sheet.pk}&stage={self.stage.pk}')
        self.assertEqual(result.data['results'][0]['id'], self.source.pk)
        BudgetSheet.objects.filter(pk=self.sheet.pk).update(status='DRAFT')
        response = self.client.post(self.base, {'creation_key': str(uuid.uuid4()), 'budget_sheet': self.sheet.pk,
                    'reference_date': '2026-10-28'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_rental_requires_period_and_catalog_flag(self):
        self.supply.legacy_payload = {'insumoLocacao': 1}
        self.supply.save()
        rev, _ = self.create(is_rental=True)
        rev = self.post(rev, 'sections', {'source_stage': self.stage.pk, 'description': 'Descrição geral livre'})
        action = f"sections/{rev['sections'][0]['id']}/items"
        self.post(rev, action, {'supply': self.supply.pk, 'quantity': '1'}, expected=400)
        rev = self.post(rev, action, {'supply': self.supply.pk, 'quantity': '1', 'period': 2, 'period_unit': 'DAY'})
        self.assertEqual(rev['sections'][0]['items'][0]['period'], 2)
        response = self.client.patch(f"{self.base}{rev['id']}/", {'expected_version': rev['version'], 'is_rental': False}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_no_one_can_generate_rm_revision_after_approval(self):
        rev = self.post(self.ready(), 'submit')
        self.client.force_authenticate(self.director)
        approved = self.post(rev, 'approve')
        self.assertTrue(approved['is_approved_effective'])
        self.post(approved, 'generate-revision', {'reason': 'Tentativa da Diretoria'}, expected=400)
        self.client.force_authenticate(self.owner)
        self.post(approved, 'generate-revision', {'reason': 'Tentativa do criador'}, expected=400)

    def test_cancel_invalidates_approved_rm(self):
        rev = self.post(self.ready(), 'submit')
        self.client.force_authenticate(self.director)
        approved = self.post(rev, 'approve')
        cancelled = self.post(approved, 'cancel', {'reason': 'Cancelar RM'})
        self.assertEqual(cancelled['status'], 2)
        current = self.client.get(f"{self.base}{approved['id']}/").data
        self.assertEqual(current['effective_status'], 2)
        self.assertFalse(current['is_approved_effective'])
        self.assertIsNone(current['approved_revision'])

    def test_stale_item_add_does_not_duplicate(self):
        rev, _ = self.create()
        rev = self.post(rev, 'sections', {'source_stage': self.stage.pk, 'description': 'Descrição geral livre'})
        action = f"sections/{rev['sections'][0]['id']}/items"
        self.post(rev, action, {'supply': self.supply.pk, 'quantity': '1'})
        self.post(rev, action, {'supply': self.supply.pk, 'quantity': '1'}, expected=409)
        self.assertEqual(MaterialRequisitionRevision.objects.get(pk=rev['id']).sections.get().items.count(), 1)

    def test_reorder_requires_exact_context(self):
        rev = self.ready()
        section = rev['sections'][0]['id']
        first = rev['sections'][0]['items'][0]['id']
        rev = self.post(rev, f'sections/{section}/items', {'supply': self.supply.pk, 'quantity': '1'})
        second = rev['sections'][0]['items'][1]['id']
        self.post(rev, f'sections/{section}/reorder-items', {'order': [first, first]}, expected=400)
        reordered = self.post(rev, f'sections/{section}/reorder-items', {'order': [second, first]})
        self.assertEqual([x['id'] for x in reordered['sections'][0]['items']], [second, first])

    def test_invalid_json_body_is_validation_error(self):
        response = self.client.post(self.base, [], format='json')
        self.assertEqual(response.status_code, 400)

    def test_automatic_origin_ignores_newer_draft_revision(self):
        from django.utils import timezone
        from datetime import timedelta
        BudgetSheet.objects.filter(pk=self.sheet.pk).update(finalized_at=timezone.now() - timedelta(days=2))
        finalized = BudgetSheet.objects.create(number=self.sheet.number, proposal=self.proposal,
            proposal_sequence=self.sheet.proposal_sequence, revision=1,
            revision_root=self.sheet, previous_revision=self.sheet)
        BudgetSheet.objects.filter(pk=finalized.pk).update(status='FINALIZED', finalized_at=timezone.now())
        BudgetSheet.objects.create(number=self.sheet.number, proposal=self.proposal,
            proposal_sequence=self.sheet.proposal_sequence, revision=2,
            revision_root=self.sheet, previous_revision=finalized)
        rev, _ = self.create()
        self.assertEqual(rev['budget_sheet'], finalized.pk)
        result = self.client.get(self.base + f'context/?proposal={self.proposal.pk}')
        self.assertEqual(result.data['count'], 1)
        self.assertEqual(result.data['results'][0]['id'], finalized.pk)

    def test_most_recent_finalized_family_and_other_pc_are_isolated(self):
        from django.utils import timezone
        from datetime import timedelta
        BudgetSheet.objects.filter(pk=self.sheet.pk).update(finalized_at=timezone.now() - timedelta(days=1))
        other = BudgetSheet.objects.create(number='NEW', proposal=self.proposal)
        BudgetSheet.objects.filter(pk=other.pk).update(status='FINALIZED', finalized_at=timezone.now())
        foreign_pc = Proposal.objects.create(code='PC26002', party=self.party,
            entry_date=date(2026, 10, 28), work_name='Outra obra')
        foreign = BudgetSheet.objects.create(number='FOREIGN', proposal=foreign_pc)
        BudgetSheet.objects.filter(pk=foreign.pk).update(status='FINALIZED', finalized_at=timezone.now() + timedelta(hours=1))
        rev, _ = self.create()
        self.assertEqual(rev['budget_sheet'], other.pk)

    def test_origin_race_returns_conflict_and_retry_keeps_original(self):
        from django.utils import timezone
        rev, data = self.create(expected_budget_sheet=self.sheet.pk)
        other = BudgetSheet.objects.create(number='NEW', proposal=self.proposal)
        BudgetSheet.objects.filter(pk=other.pk).update(status='FINALIZED', finalized_at=timezone.now())
        # Retry da mesma criação recupera a RM, sem selecionar outra origem.
        retry = self.client.post(self.base, data, format='json')
        self.assertEqual(retry.status_code, 201, retry.data)
        self.assertEqual(retry.data['id'], rev['id'])
        self.assertEqual(retry.data['budget_sheet'], self.sheet.pk)
        stale = dict(data, creation_key=str(uuid.uuid4()))
        self.assertEqual(self.client.post(self.base, stale, format='json').status_code, 409)
        self.assertEqual(MaterialRequisition.objects.count(), 1)
        # A RM existente continua podendo consultar a origem congelada.
        self.assertEqual(self.client.get(self.base + f'context/?budget_sheet={self.sheet.pk}').status_code, 200)

    def test_no_finalized_origin_is_validation_error(self):
        BudgetSheet.objects.filter(pk=self.sheet.pk).update(status='DRAFT')
        response = self.client.post(self.base, {'proposal': self.proposal.pk,
            'creation_key': str(uuid.uuid4()), 'reference_date': '2026-10-28'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(MaterialRequisition.objects.count(), 0)

    def test_cannot_choose_old_sheet_through_compatibility_field(self):
        from django.utils import timezone
        other = BudgetSheet.objects.create(number='NEW', proposal=self.proposal)
        BudgetSheet.objects.filter(pk=other.pk).update(status='FINALIZED', finalized_at=timezone.now())
        response = self.client.post(self.base, {'budget_sheet': self.sheet.pk,
            'creation_key': str(uuid.uuid4()), 'reference_date': '2026-10-28'}, format='json')
        self.assertEqual(response.status_code, 409)

    def test_free_description_and_stage_only_section(self):
        rev, _ = self.create()
        rev = self.post(rev, 'sections', {'source_stage': self.stage.pk, 'description': '  Texto digitado livremente  '})
        section = rev['sections'][0]
        self.assertIsNone(section['source_composition'])
        self.assertEqual(section['description'], 'Texto digitado livremente')
        self.assertEqual(section['composition_snapshot']['scope'], 'stage')
        self.post(rev, 'sections', {'source_stage': self.stage.pk, 'description': '   '}, expected=400)

    def test_supplies_restricted_to_stage_direct_items_and_composition_leaves(self):
        direct = Supply.objects.create(description='Areia da etapa', unit='KG', supply_type='MATERIAL')
        BudgetSheetStageItem.objects.create(budget_sheet_stage=self.stage, item_type='SUPPLY', supply=direct,
            description_snapshot='Areia da etapa', unit_snapshot='KG', quantity=5, order=2)
        foreign = Supply.objects.create(description='Fora da etapa', unit='UN', supply_type='MATERIAL')
        another_stage = BudgetSheetStage.objects.create(budget_sheet=self.sheet,
            stage=BudgetStageCatalog.objects.create(name='Outra etapa'), order=2)
        BudgetSheetStageItem.objects.create(budget_sheet_stage=another_stage, item_type='SUPPLY', supply=foreign,
            description_snapshot='Fora da etapa', unit_snapshot='UN', quantity=1, order=1)
        rev, _ = self.create()
        rev = self.post(rev, 'sections', {'source_stage': self.stage.pk, 'description': 'Minha descrição'})
        section = rev['sections'][0]['id']
        endpoint = f"{self.base}{rev['id']}/sections/{section}/supplies/"
        result = self.client.get(endpoint)
        self.assertEqual({row['id'] for row in result.data['results']}, {self.supply.pk, direct.pk})
        self.assertEqual(self.client.get(endpoint, {'search': 'Areia'}).data['count'], 1)
        self.assertEqual(self.client.get(endpoint, {'search': 'Fora'}).data['count'], 0)
        before_version = rev['version']
        self.post(rev, f'sections/{section}/items', {'supply': foreign.pk, 'quantity': '1'}, expected=400)
        self.assertEqual(MaterialRequisitionRevision.objects.get(pk=rev['id']).version, before_version)
        row = next(row for row in result.data['results'] if row['id'] == direct.pk)
        rev = self.post(rev, f'sections/{section}/items', {'supply': direct.pk, 'quantity': '2', 'source_path': row['source_path']})
        self.assertEqual(rev['sections'][0]['items'][0]['description'], 'Areia da etapa')

    def test_quantity_cannot_exceed_po_in_insert_or_edit(self):
        BudgetSheetStageItem.objects.filter(pk=self.source.pk).update(quantity=Decimal('0.5'))
        rev, _ = self.create()
        rev = self.post(rev, 'sections', {'source_stage': self.stage.pk, 'description': 'Limite PO'})
        section = rev['sections'][0]['id']
        action = f'sections/{section}/items'
        failure = self.post(rev, action, {'supply': self.supply.pk, 'quantity': '1.000001'}, expected=400)
        self.assertIn('quantity', failure)
        rev = self.post(rev, action, {'supply': self.supply.pk, 'quantity': '1'})
        item = rev['sections'][0]['items'][0]
        self.assertEqual(Decimal(item['max_quantity']), Decimal('1'))
        endpoint = f"{self.base}{rev['id']}/items/{item['id']}/"
        failure = self.client.patch(endpoint, {
            'expected_version': rev['version'], 'quantity': '2',
        }, format='json')
        self.assertEqual(failure.status_code, 400)
        self.assertIn('quantity', failure.data)
        updated = self.client.patch(endpoint, {
            'expected_version': rev['version'], 'quantity': '0.75',
        }, format='json')
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(Decimal(updated.data['sections'][0]['items'][0]['quantity']), Decimal('0.75'))

    def test_supplies_skip_disabled_ancestors_duplicates_and_inactive_catalog(self):
        snapshot = deepcopy(self.source.composition_snapshot)
        supply_row = next(row for row in snapshot['items'] if row.get('supply_id') == self.supply.pk)
        snapshot['items'].append(dict(supply_row, source_path='dup'))
        hidden = Supply.objects.create(description='Filho desabilitado', supply_type='MATERIAL', unit='UN')
        snapshot['items'].extend([
            {'source_path': 'group', 'display_only': True, 'enabled': False},
            dict(supply_row, source_path='group.1', supply_id=hidden.pk),
        ])
        BudgetSheetStageItem.objects.filter(pk=self.source.pk).update(composition_snapshot=snapshot)
        rev, _ = self.create()
        rev = self.post(rev, 'sections', {'source_stage': self.stage.pk, 'description': 'Descrição'})
        section = rev['sections'][0]['id']
        endpoint = f"{self.base}{rev['id']}/sections/{section}/supplies/"
        result = self.client.get(endpoint)
        self.assertEqual([row['id'] for row in result.data['results']], [self.supply.pk])
        self.post(rev, f'sections/{section}/items', {'supply': hidden.pk, 'quantity': '1'}, expected=400)
        Supply.objects.filter(pk=self.supply.pk).update(is_active=False)
        self.assertEqual(self.client.get(endpoint).data['count'], 0)

    def test_description_edit_version_authorization_audit_and_approval_lock(self):
        rev = self.ready()
        section = rev['sections'][0]['id']
        endpoint = f"{self.base}{rev['id']}/sections/{section}/"
        patch = {'expected_version': rev['version'], 'description': 'Texto novo sem composição'}
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.patch(endpoint, patch, format='json').status_code, 403)
        self.client.force_authenticate(self.owner)
        changed = self.client.patch(endpoint, patch, format='json')
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual(changed.data['sections'][0]['description'], patch['description'])
        self.assertTrue(MaterialRequisitionEvent.objects.filter(revision_id=rev['id'], action='UPDATE_SECTION').exists())
        self.assertEqual(self.client.patch(endpoint, patch, format='json').status_code, 409)
        pending = self.post(changed.data, 'submit')
        self.client.force_authenticate(self.director)
        approved = self.post(pending, 'approve')
        response = self.client.patch(endpoint, {
            'expected_version': approved['version'], 'description': 'Alteração após aprovação'
        }, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get(f"{self.base}{approved['id']}/").data['sections'][0]['description'], patch['description'])

    def test_supplies_context_cannot_use_section_of_another_rm(self):
        first = self.ready()
        second, _ = self.create()
        result = self.client.get(f"{self.base}{second['id']}/sections/{first['sections'][0]['id']}/supplies/")
        self.assertEqual(result.status_code, 404)

    def test_historical_composition_sections_preserve_text_and_items(self):
        from material_requisitions.models import MaterialRequisitionSection
        rev, _ = self.create()
        old = MaterialRequisitionSection.objects.create(revision_id=rev['id'], source_stage=self.stage,
            source_composition=self.source, stage_name='Etapa antiga', description='Descrição preservada',
            unit='VB', composition_snapshot=self.source.composition_snapshot, position=1)
        result = self.client.get(f"{self.base}{rev['id']}/sections/{old.pk}/supplies/")
        self.assertEqual([row['id'] for row in result.data['results']], [self.supply.pk])
        old.refresh_from_db()
        self.assertEqual(old.description, 'Descrição preservada')
        self.assertEqual(old.source_composition_id, self.source.pk)
        self.assertEqual(old.composition_snapshot, self.source.composition_snapshot)

    def test_stage_autocomplete_respects_three_request_types(self):
        for typ, expected in [(0, {self.supply.pk}), (1, {self.service.pk}), (2, {self.supply.pk, self.service.pk})]:
            rev, _ = self.create(request_type=typ)
            rev = self.post(rev, 'sections', {'source_stage': self.stage.pk, 'description': 'Etapa do tipo'})
            section = rev['sections'][0]['id']
            response = self.client.get(f"{self.base}{rev['id']}/sections/{section}/supplies/")
            self.assertEqual({row['id'] for row in response.data['results']}, expected)
