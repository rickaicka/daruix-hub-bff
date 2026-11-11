from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import unicodedata

from django.conf import settings
from django.db import transaction
from django.db.models import Max, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from budgeting.models import BudgetSheet, BudgetSheetStage, BudgetSheetStageItem, Supply
from material_requisitions.models import (MaterialRequisition as Root, MaterialRequisitionRevision as Revision,
    MaterialRequisitionSection as Section, MaterialRequisitionItem as Item,
    MaterialRequisitionEvent as Event, RMStatus as Status, RMType)
from commercial.models import Proposal


class Conflict(APIException):
    status_code = 409
    default_detail = 'Conteúdo alterado ou revisão desatualizada. Recarregue a RM.'


def privileged(user):
    if user.is_superuser:
        return True
    group = user.group
    if not group or not group.is_active:
        return False
    name = ''.join(c for c in unicodedata.normalize('NFKD', group.name)
                   if not unicodedata.combining(c)).strip().casefold()
    allowed = getattr(settings, 'RM_MANAGER_GROUP_NAMES',
                      ['diretoria', 'adm', 'administrador', 'gestao'])
    return name in allowed


def is_directoria_collaborator(user):
    """Exceção de aprovação: colaborador do grupo ativo DIRETORIA."""
    group = getattr(user, 'group', None)
    if getattr(user, 'user_type', None) != 'COLABORADOR' or not group or not group.is_active:
        return False
    normalized = ''.join(c for c in unicodedata.normalize('NFKD', group.name)
                         if not unicodedata.combining(c)).strip().casefold()
    return normalized == 'diretoria'


def can_decide_rm(rev, user):
    """Autorização de decisão, compartilhada entre API, serializer e notificações.

    Responsável técnico da Proposta OU colaborador da DIRETORIA, com permissão
    explícita. Criador e solicitante nunca podem decidir a própria RM.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return False
    root = rev.requisition
    if root.cancelled_at or root.current_revision_id != rev.pk or rev.status != Status.PENDING:
        return False
    if user.pk in (rev.owner_id, root.requester_id):
        return False
    code = getattr(settings, 'RM_APPROVE_PERMISSION_CODE', 'material_requisition.approve')
    if not user.has_permission_code(code):
        return False
    # Fonte de verdade: Cadastro de Proposta, sem depender da PO.
    proposal = root.proposal
    return (proposal is not None and proposal.technical_responsible_id == user.pk) or is_directoria_collaborator(user)


def _event(rev, user, action, reason='', payload=None):
    Event.objects.create(revision=rev, actor=user, action=action, version=rev.version,
                         reason=reason, payload=payload or {})


def _bump(rev, user, action, reason='', payload=None):
    rev.version += 1
    rev.save()
    _event(rev, user, action, reason, payload)
    return rev


def _lock(pk, expected):
    # Ordem única de bloqueio para todas as operações: família e depois revisão.
    family_id = Revision.objects.values_list('requisition_id', flat=True).get(pk=pk)
    root = Root.objects.select_for_update().get(pk=family_id)
    rev = Revision.objects.select_for_update().get(pk=pk)
    if root.cancelled_at or root.current_revision_id != rev.pk or rev.version != expected:
        raise Conflict()
    return root, rev


def _editable(rev, user):
    if rev.status not in (Status.DRAFT, Status.PENDING) or rev.owner_id != user.pk:
        raise PermissionDenied('Somente o criador pode editar rascunho ou RM aguardando aprovação.')


def _validate_header(rev):
    if rev.request_type not in RMType.values:
        raise ValidationError({'request_type': 'Tipo inválido.'})
    if rev.delivery_date and rev.delivery_date < rev.reference_date:
        raise ValidationError({'delivery_date': 'Entrega anterior à data da RM.'})
    if rev.is_rental and rev.request_type != RMType.MATERIAL:
        raise ValidationError({'is_rental': 'Locação exige RM de Material.'})


def _allowed(rev, supply_type):
    mapping = getattr(settings, 'RM_SUPPLY_TYPE_MAP', {
        'MATERIAL': ['MATERIAL'], 'SERVICE': ['SERVICE', 'LABOR'],
    })
    choices = (mapping['MATERIAL'] if rev.request_type == 0 else mapping['SERVICE']
               if rev.request_type == 1 else mapping['MATERIAL'] + mapping['SERVICE'])
    return supply_type in choices


def _validate_item(rev, item):
    if not _allowed(rev, item.supply_type):
        raise ValidationError('Item incompatível com o tipo da RM.')
    if not item.unit.strip() or not item.description.strip() or item.quantity <= 0:
        raise ValidationError('Descrição, unidade e quantidade positiva são obrigatórias.')
    if rev.is_rental:
        rental = item.supply.legacy_payload.get('insumoLocacao')
        if str(rental).lower() not in ('1', '-1', 'true', 'sim'):
            raise ValidationError('O insumo não está identificado como item de locação no catálogo.')
        if not item.period or item.period_unit not in ('HOUR', 'DAY', 'WEEK', 'MONTH'):
            raise ValidationError('Informe período positivo e unidade de período para locação.')
    elif item.period is not None or item.period_unit:
        raise ValidationError('Período só pode ser preenchido para locação.')


def latest_finalized_sheet(proposal_id):
    """Última revisão finalizada por família; entre famílias, a finalização mais recente."""
    latest_revision = BudgetSheet.objects.filter(
        proposal_id=OuterRef('proposal_id'),
        proposal_sequence=OuterRef('proposal_sequence'), status='FINALIZED',
    ).order_by('-revision', '-id').values('pk')[:1]
    return (BudgetSheet.objects.filter(proposal_id=proposal_id, status='FINALIZED')
        .filter(pk=Subquery(latest_revision))
        .annotate(finalized_order=Coalesce('finalized_at', 'created_at'))
        .order_by('-finalized_order', '-proposal_sequence', '-revision', '-id').first())


def _eligible_sheet(sheet):
    # RMs existentes mantêm a origem congelada, mesmo se outra PO for finalizada.
    if not sheet.proposal_id or sheet.status != 'FINALIZED':
        raise ValidationError('A origem da RM precisa ser uma PO finalizada vinculada ao PC.')


def _automatic_sheet(proposal_id):
    sheet = latest_finalized_sheet(proposal_id)
    if sheet is None:
        raise ValidationError({'proposal': 'Este PC não possui Planilha de Orçamento finalizada.'})
    return sheet


@transaction.atomic
def create(user, data):
    proposal_id = data.get('proposal')
    if proposal_id is None:
        proposal_id = BudgetSheet.objects.values_list('proposal_id', flat=True).get(pk=data['budget_sheet'])
    if proposal_id is None:
        raise ValidationError('PO sem PC.')
    # Mesma trava da numeração por PC; idempotência antes de resolver novamente a origem.
    proposal = Proposal.objects.select_for_update().get(pk=proposal_id)
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    existing = Root.objects.filter(creation_key=data['creation_key']).first()
    if existing:
        if existing.requester_id != user.pk or existing.creation_hash != digest:
            raise Conflict('Chave de criação já usada por outra solicitação.')
        return existing.revisions.get(number=0)
    sheet = _automatic_sheet(proposal.pk)
    for field in ('budget_sheet', 'expected_budget_sheet'):
        if field in data and data[field] != sheet.pk:
            raise Conflict('A última PO finalizada do PC mudou. Recarregue o contexto antes de criar a RM.')
    sequence = (Root.objects.filter(proposal=proposal).aggregate(n=Max('sequence'))['n'] or 0) + 1
    root = Root.objects.create(proposal=proposal, sequence=sequence, requester=user,
        number=f'RM-{proposal.code}-{sequence:03}', creation_key=data['creation_key'], creation_hash=digest)
    rev = Revision(requisition=root, budget_sheet=sheet, owner=user,
        reference_date=data['reference_date'], delivery_date=data.get('delivery_date'),
        request_type=data.get('request_type', 0), notes=data.get('notes', ''),
        is_rental=data.get('is_rental', False), source_snapshot={
            'proposal_id': proposal.pk, 'pc': proposal.code, 'work_name': proposal.work_name,
            'party_id': proposal.party_id, 'client': proposal.party.legal_name,
            'budget_sheet_id': sheet.pk, 'budget_number': sheet.number,
            'budget_revision': sheet.revision})
    _validate_header(rev)
    rev.save()
    root.current_revision = rev
    root.save(update_fields=['current_revision'])
    _event(rev, user, 'CREATE')
    return rev


@transaction.atomic
def update_header(pk, expected, user, data):
    _, rev = _lock(pk, expected)
    _editable(rev, user)
    before = {k: str(getattr(rev, k)) for k in data}
    for key, value in data.items():
        setattr(rev, key, value)
    _validate_header(rev)
    for item in Item.objects.filter(section__revision=rev).select_related('supply'):
        _validate_item(rev, item)
    return _bump(rev, user, 'UPDATE_HEADER', payload={'before': before,
        'after': {k: str(getattr(rev, k)) for k in data}})


def stage_snapshot(stage):
    """Insumos diretos + folhas habilitadas dos snapshots da PO, sem catálogo global."""
    rows = []
    for source in stage.items.select_related('supply').order_by('order', 'id'):
        prefix = f'po.{source.pk}'
        if source.item_type == 'SUPPLY' and source.supply_id:
            rows.append({'source_path': prefix, 'supply_id': source.supply_id,
                'description_snapshot': source.description_snapshot,
                'unit_snapshot': source.unit_snapshot, 'coefficient': str(source.quantity),
                'enabled': True, 'display_only': False})
        elif source.item_type == 'SERVICE_COMPOSITION':
            components = source.composition_snapshot.get('items', [])
            by_path = {str(row.get('source_path', '')): row for row in components}
            for row in components:
                path = str(row.get('source_path', ''))
                parts = path.split('.')
                if (row.get('display_only') or not row.get('supply_id') or not row.get('enabled', True)
                        or any(not by_path.get('.'.join(parts[:i]), {}).get('enabled', True)
                               for i in range(1, len(parts)))):
                    continue
                quantity = (Decimal(str(row.get('coefficient', 0))) * source.quantity).quantize(
                    Decimal('0.000001'), rounding=ROUND_HALF_UP)
                rows.append({'source_path': f'{prefix}.{path}', 'supply_id': row['supply_id'],
                    'description_snapshot': row.get('description_snapshot', ''),
                    'unit_snapshot': row.get('unit_snapshot', ''), 'coefficient': str(quantity),
                    'enabled': True, 'display_only': False})
    return {'scope': 'stage', 'stage_id': stage.pk, 'budget_sheet_id': stage.budget_sheet_id, 'items': rows}


def section_stage_snapshot(section):
    snapshot = section.composition_snapshot
    if snapshot.get('scope') == 'stage' and snapshot.get('stage_id') == section.source_stage_id:
        return snapshot
    # Etapas históricas eram vinculadas a uma composição: consulta a etapa inteira da PO
    # congelada, sem reescrever sua descrição, snapshot ou itens já gravados.
    return stage_snapshot(section.source_stage)


def section_quantity_limits(section):
    return {
        (row['source_path'], row['supply_id']): Decimal(str(row['coefficient']))
        for row in section_stage_snapshot(section).get('items', [])
        if row.get('supply_id') and row.get('source_path')
    }


def item_quantity_limit(section, limits, source_path, supply_id):
    if source_path and not source_path.startswith('po.') and section.source_composition_id:
        source_path = f'po.{section.source_composition_id}.{source_path}'
    return limits.get((source_path, supply_id))


def _validate_quantity_limit(quantity, limit):
    if limit is None:
        raise ValidationError({'quantity': 'Não foi possível identificar a quantidade deste item na PO de origem.'})
    if quantity > limit:
        maximum = format(limit.normalize(), 'f')
        raise ValidationError({'quantity': f'A quantidade máxima deste item na PO é {maximum.replace(".", ",")}.'})


def section_supply_options(section, rev, search=''):
    rows = section_stage_snapshot(section).get('items', [])
    supplies = Supply.objects.in_bulk({row['supply_id'] for row in rows if row.get('supply_id')})
    result = {}
    term = search.strip().casefold()
    for row in rows:
        supply = supplies.get(row.get('supply_id'))
        if not supply or not supply.is_active or not _allowed(rev, supply.supply_type):
            continue
        if rev.is_rental and str(supply.legacy_payload.get('insumoLocacao')).lower() not in ('1', '-1', 'true', 'sim'):
            continue
        description = row.get('description_snapshot') or supply.description
        result.setdefault(supply.pk, {'id': supply.pk, 'description': description,
            'unit': row.get('unit_snapshot') or supply.unit, 'supply_type': supply.supply_type,
            'source_path': row['source_path'], 'max_quantity': str(row['coefficient'])})
    matches = [value for value in result.values() if not term or term in value['description'].casefold()
               or term in supplies[value['id']].description.casefold()]
    return sorted(matches, key=lambda value: (value['description'].casefold(), value['id']))


@transaction.atomic
def add_section(pk, expected, user, source_stage, description):
    _, rev = _lock(pk, expected)
    _editable(rev, user)
    stage = BudgetSheetStage.objects.get(pk=source_stage, budget_sheet_id=rev.budget_sheet_id)
    description = description.strip()
    if not description or len(description) > 500:
        raise ValidationError({'description': 'Informe uma descrição geral com até 500 caracteres.'})
    if Section.objects.filter(revision=rev, source_stage=stage, description=description).exists():
        raise ValidationError('Já existe uma etapa da RM com a mesma origem e descrição geral.')
    position = (rev.sections.aggregate(n=Max('position'))['n'] or 0) + 1
    section = Section.objects.create(revision=rev, source_stage=stage, source_composition=None,
        stage_name=stage.name_snapshot, description=description, unit='',
        composition_snapshot=stage_snapshot(stage), position=position)
    _bump(rev, user, 'ADD_SECTION', payload={'section': section.pk, 'source_stage': stage.pk,
        'description': description})
    return rev


@transaction.atomic
def update_section(pk, expected, user, section_id, description):
    _, rev = _lock(pk, expected)
    _editable(rev, user)
    section = Section.objects.get(pk=section_id, revision=rev)
    description = description.strip()
    if not description or len(description) > 500:
        raise ValidationError({'description': 'Informe uma descrição geral com até 500 caracteres.'})
    before = section.description
    section.description = description
    section.save(update_fields=['description'])
    return _bump(rev, user, 'UPDATE_SECTION', payload={'section': section.pk,
        'before': {'description': before}, 'after': {'description': description}})


def _item_snapshot(item):
    return {'id': item.pk, 'lineage': str(item.lineage), 'supply': item.supply_id,
            'description': item.description, 'unit': item.unit, 'supply_type': item.supply_type,
            'quantity': str(item.quantity), 'period': item.period, 'period_unit': item.period_unit,
            'notes': item.notes, 'source_path': item.source_path, 'position': item.position}


def _quantity(value):
    try:
        qty = Decimal(str(value))
        if (not qty.is_finite() or qty <= 0 or qty >= Decimal('1000000000000')
                or qty != qty.quantize(Decimal('0.000001'))):
            raise ValueError()
        return qty.quantize(Decimal('0.000001'))
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError('Quantidade deve ser positiva, com até seis casas decimais.')


@transaction.atomic
def add_item(pk, expected, user, section_id, data):
    _, rev = _lock(pk, expected)
    _editable(rev, user)
    section = Section.objects.get(pk=section_id, revision=rev)
    supply = Supply.objects.get(pk=data['supply'], is_active=True)
    options = section_supply_options(section, rev)
    source_path = data.get('source_path', '')
    option = next((row for row in options if row['id'] == supply.pk
                   and (not source_path or row['source_path'] == source_path)), None)
    if option is None:
        raise ValidationError({'supply': 'O insumo deve pertencer à etapa selecionada na PO de origem e ser compatível com a RM.'})
    description, unit, source_path = option['description'], option['unit'], option['source_path']
    item = Item(section=section, supply=supply, description=description, unit=unit,
        supply_type=supply.supply_type, quantity=_quantity(data['quantity']),
        period=data.get('period'), period_unit=data.get('period_unit', ''),
        notes=data.get('notes', ''), source_path=source_path,
        position=(section.items.aggregate(n=Max('position'))['n'] or 0) + 1)
    _validate_item(rev, item)
    _validate_quantity_limit(item.quantity, Decimal(option['max_quantity']))
    item.full_clean()
    item.save()
    _bump(rev, user, 'ADD_ITEM', payload=_item_snapshot(item))
    return rev


@transaction.atomic
def change_item(pk, expected, user, item_id, data=None):
    _, rev = _lock(pk, expected)
    _editable(rev, user)
    item = Item.objects.select_related('supply').get(pk=item_id, section__revision=rev)
    before = _item_snapshot(item)
    if data is None:
        item.delete()
        return _bump(rev, user, 'DELETE_ITEM', payload=before)
    for key, value in data.items():
        setattr(item, key, _quantity(value) if key == 'quantity' else value)
    _validate_item(rev, item)
    if item.source_path:
        _validate_quantity_limit(item.quantity, item_quantity_limit(
            item.section, section_quantity_limits(item.section), item.source_path, item.supply_id,
        ))
    item.full_clean()
    item.save()
    return _bump(rev, user, 'UPDATE_ITEM', payload={'before': before, 'after': _item_snapshot(item)})


@transaction.atomic
def remove_section(pk, expected, user, section_id):
    _, rev = _lock(pk, expected)
    _editable(rev, user)
    section = Section.objects.get(pk=section_id, revision=rev)
    stage_items = section.items.all()
    items = [_item_snapshot(item) for item in stage_items]
    stage_items.delete()
    section.delete()
    return _bump(rev, user, 'DELETE_SECTION', payload={
        'section': int(section_id),
        'description': section.description,
        'items': items,
    })


def _ready(rev, *, check_quantity_limits=True):
    _validate_header(rev)
    sections = list(rev.sections.all())
    if not sections or any(not s.items.exists() for s in sections):
        raise ValidationError('Adicione pelo menos uma etapa e inclua um item em cada etapa.')
    for section in sections:
        limits = section_quantity_limits(section) if check_quantity_limits else {}
        for item in section.items.select_related('supply'):
            _validate_item(rev, item)
            if check_quantity_limits and item.source_path:
                _validate_quantity_limit(item.quantity, item_quantity_limit(
                    section, limits, item.source_path, item.supply_id,
                ))


@transaction.atomic
def decide(pk, expected, user, action, reason=''):
    root, rev = _lock(pk, expected)
    reason = reason.strip()
    if action == 'submit':
        _editable(rev, user)
        if rev.status != Status.DRAFT:
            raise Conflict('RM já enviada.')
        _ready(rev)
        rev.status = Status.PENDING
    elif action in ('approve', 'reject'):
        if not can_decide_rm(rev, user):
            raise PermissionDenied('Somente o responsável técnico da proposta ou um colaborador da Diretoria, com permissão RM e diferente do criador/solicitante, pode decidir.')
        if rev.status != Status.PENDING:
            raise Conflict('A decisão exige RM aguardando aprovação.')
        if action == 'reject' and not reason:
            raise ValidationError('Informe o motivo da reprovação.')
        _ready(rev, check_quantity_limits=action == 'approve')
        rev.status = Status.APPROVED if action == 'approve' else Status.REJECTED
        if action == 'approve':
            root.approved_revision = rev
            root.save(update_fields=['approved_revision'])
    elif action == 'cancel':
        if not privileged(user) and not (rev.owner_id == user.pk and rev.status in (Status.DRAFT, Status.PENDING)):
            raise PermissionDenied('Sem permissão para cancelar esta RM.')
        if not reason:
            raise ValidationError('Informe o motivo do cancelamento.')
        root.cancelled_at = timezone.now()
        root.approved_revision = None
        root.save(update_fields=['cancelled_at', 'approved_revision'])
        rev.status = Status.CANCELLED
    else:
        raise ValidationError('Ação inválida.')
    return _bump(rev, user, action.upper(), reason)


def new_revision(pk, expected, user, reason):
    """RM is a single document. Retained for compatibility with old imports."""
    raise ValidationError('Requisições de materiais não possuem revisão. Consulte o histórico de operações.')


@transaction.atomic
def load_composition(
    pk, expected, user, section_id, multiplier, period=None, period_unit='',
    recalculate=False, source_paths=None,
):
    _, rev = _lock(pk, expected)
    _editable(rev, user)
    section = Section.objects.get(pk=section_id, revision=rev)
    rows = section.composition_snapshot.get('items', [])
    limits = section_quantity_limits(section)
    factor = _quantity(multiplier)
    by_path = {row.get('source_path'): row for row in rows}
    linked_items = list(section.items.exclude(source_path='').order_by('pk'))
    if source_paths is not None:
        selected_paths = set(source_paths)
        if not selected_paths or len(selected_paths) != len(source_paths):
            raise ValidationError({'source_paths': 'Selecione componentes sem duplicar.'})
        if selected_paths.difference(by_path):
            raise ValidationError({'source_paths': 'Há componentes que não pertencem a esta etapa.'})
        rows = [row for row in rows if row.get('source_path') in selected_paths]
        linked_items = [item for item in linked_items if item.source_path in selected_paths]

    if linked_items and not recalculate:
        raise Conflict('Confirme o recálculo para atualizar as quantidades dos itens vinculados à PO.')
    if recalculate and not linked_items:
        raise ValidationError('Não há itens vinculados à PO para recalcular.')
    supplies = Supply.objects.in_bulk([x.get('supply_id') for x in rows if x.get('supply_id')])
    objects, skipped = [], []
    candidates = {}
    pos = section.items.aggregate(n=Max('position'))['n'] or 0
    for row in rows:
        path = str(row.get('source_path', ''))
        parts = path.split('.')
        reason = None
        supply = supplies.get(row.get('supply_id'))
        if row.get('display_only'):
            if source_paths is not None:
                skipped.append({'source_path': path, 'reason': 'display_only'})
            continue
        if not row.get('enabled', True) or any(not by_path.get('.'.join(parts[:i]), {}).get('enabled', True)
                                              for i in range(1, len(parts))):
            reason = 'disabled'
        elif not supply or not supply.is_active:
            reason = 'supply_unavailable'
        elif not _allowed(rev, supply.supply_type):
            reason = 'incompatible_type'
        elif Decimal(str(row.get('coefficient', 0))) <= 0:
            reason = 'zero_quantity'
        if reason:
            skipped.append({'source_path': path, 'reason': reason})
            continue
        quantity = Decimal(str(row['coefficient'])) * factor
        _validate_quantity_limit(quantity, item_quantity_limit(section, limits, path, supply.pk))
        pos += 1
        item = Item(section=section, supply=supply, supply_type=supply.supply_type,
            description=row.get('description_snapshot') or supply.description,
            unit=row.get('unit_snapshot') or supply.unit,
            quantity=_quantity(quantity),
            period=period, period_unit=period_unit, source_path=path, position=pos)
        _validate_item(rev, item)
        item.full_clean()
        objects.append(item)
        candidates[path] = item
    changes = []
    if recalculate:
        existing_paths = {item.source_path for item in linked_items}
        if len(existing_paths) != len(linked_items) or (
            source_paths is None and existing_paths != candidates.keys()
        ):
            raise Conflict('Os itens vinculados diferem da origem congelada. Recalcule manualmente ou revise os vínculos.')
        updated_items = []
        for current in linked_items:
            calculated = candidates.pop(current.source_path, None)
            if calculated is None:
                continue
            if current.supply_id != calculated.supply_id:
                raise Conflict('Um componente vinculado não corresponde mais ao insumo da PO de origem.')
            before = str(current.quantity)
            current.quantity = calculated.quantity
            if rev.is_rental:
                current.period, current.period_unit = calculated.period, calculated.period_unit
            _validate_item(rev, current)
            current.full_clean()
            updated_items.append(current)
            changes.append({'id': current.pk, 'source_path': current.source_path,
                            'before': before, 'after': str(current.quantity)})
        if updated_items:
            fields = ['quantity', 'period', 'period_unit'] if rev.is_rental else ['quantity']
            Item.objects.bulk_update(updated_items, fields)
        objects = list(candidates.values())

    if not objects and not changes:
        raise ValidationError({'components': 'Não há itens requisitáveis compatíveis na seleção.', 'skipped': skipped})
    if objects:
        Item.objects.bulk_create(objects)
    report = {'added': len(objects), 'updated': len(changes), 'skipped': skipped}
    action = 'RECALCULATE_COMPOSITION' if changes else 'LOAD_COMPOSITION'
    _bump(rev, user, action, payload={
        'section': section.pk, 'multiplier': str(multiplier), **report,
        'changes': changes, 'items': [_item_snapshot(item) for item in objects],
    })
    return rev, report


@transaction.atomic
def reorder(pk, expected, user, order, section_id=None):
    _, rev = _lock(pk, expected)
    _editable(rev, user)
    if section_id is None:
        query = rev.sections.all()
    else:
        section = Section.objects.get(pk=section_id, revision=rev)
        query = section.items.all()
    objects = list(query)
    if len(order) != len(set(order)) or set(order) != {x.pk for x in objects}:
        raise ValidationError('A ordem deve conter todos os IDs do contexto, sem duplicar.')
    positions = {pk: i for i, pk in enumerate(order, 1)}
    for obj in objects:
        obj.position = positions[obj.pk]
    query.model.objects.bulk_update(objects, ['position'])
    return _bump(rev, user, 'REORDER', payload={'section': section_id, 'order': order})
