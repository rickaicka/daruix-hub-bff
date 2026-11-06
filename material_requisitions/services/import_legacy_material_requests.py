"""Importa um espelho legado de RM. Nunca altera RMs operacionais ou o Access."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json

from django.db import transaction
from django.utils import timezone

from material_requisitions.models import (LegacyMaterialRequest, LegacyMaterialRequestItem,
                               LegacyMaterialRequestIssue)
from material_requisitions.services.legacy_material_requisitions import LegacyMaterialRequisitionClient


class MaterialRequestImportError(RuntimeError):
    pass


def _hash(value):
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError) as error:
        raise MaterialRequestImportError('O bridge retornou dados JSON inválidos.') from error
    return hashlib.sha256(encoded).hexdigest()


def _integer(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip('-').isdigit():
        return int(value)
    return None


def _text(value):
    return '' if value is None else str(value).strip()


@dataclass
class PreparedImport:
    headers: list
    items: list
    issues: list
    counts: dict


def prepare(client=None, page_size=500):
    """Lê todos os recursos antes de qualquer escrita; erro aborta o lote."""
    client = client or LegacyMaterialRequisitionClient.from_django_settings()
    if type(page_size) is not int or not 1 <= page_size <= 500:
        raise ValueError('page_size deve estar entre 1 e 500.')
    headers, items, issues = [], [], []
    seen_headers, seen_items = set(), set()
    occurrences = Counter()
    counts = Counter()

    def issue(reason, row):
        payload_hash = _hash(row)
        occurrences[(reason, payload_hash)] += 1
        # A contagem distingue linhas órfãs exatamente idênticas.
        identity = _hash([reason, payload_hash, occurrences[(reason, payload_hash)]])
        issues.append((identity, reason, row))
        counts['issue_' + reason] += 1

    for row in client.iter_resource('requests', page_size=page_size):
        counts['headers_read'] += 1
        pk = _integer(row.get('codRequisicao'))
        if pk is None:
            issue('header_without_id', row)
            continue
        if pk in seen_headers:
            raise MaterialRequestImportError('Cabeçalho duplicado no lote; importação cancelada.')
        seen_headers.add(pk)
        typ = 0 if row.get('reqTipo') is None else _integer(row.get('reqTipo'))
        if typ not in (0, 1, 2):
            issue('unknown_type', row)
        status = _text(row.get('status')).casefold()
        if (status not in ('aprovada', 'aguardando') or
            (status == 'aprovada' and (row.get('reqAprovada') != True or row.get('reprovar') == True)) or
            (status == 'aguardando' and row.get('reqAprovada') == True)):
            issue('ambiguous_status', row)
        headers.append((pk, row))

    for row in client.iter_resource('request-items', page_size=page_size):
        counts['items_read'] += 1
        parent = _integer(row.get('requisicaoId'))
        item = _integer(row.get('codItem'))
        if parent is None:
            issue('item_without_parent', row)
            continue
        if parent not in seen_headers:
            issue('item_parent_not_found', row)
            continue
        if item is None:
            issue('item_without_id', row)
            continue
        key = (parent, item)
        if key in seen_items:
            raise MaterialRequestImportError('Par RM/item duplicado no lote; importação cancelada.')
        seen_items.add(key)
        items.append((parent, item, row))
    counts['headers_valid'] = len(headers)
    counts['items_valid'] = len(items)
    counts['issues'] = len(issues)
    return PreparedImport(headers, items, issues, dict(counts))


def _chunks(values, size=500):
    for start in range(0, len(values), size):
        yield values[start:start + size]


@transaction.atomic
def persist(prepared):
    """Upsert em transação única. Nunca apaga linhas ausentes na origem."""
    now = timezone.now()
    for chunk in _chunks(prepared.headers):
        objects = [LegacyMaterialRequest(
            legacy_id=pk, pc=_text(row.get('pcRequisicao'))[:255],
            legacy_number=_integer(row.get('rmCodigo')),
            legacy_type=0 if row.get('reqTipo') is None else _integer(row.get('reqTipo')),
            legacy_status=_text(row.get('status'))[:255],
            raw_payload=row, payload_hash=_hash(row), imported_at=now,
        ) for pk, row in chunk]
        LegacyMaterialRequest.objects.bulk_create(objects, update_conflicts=True,
            unique_fields=['legacy_id'],
            update_fields=['pc', 'legacy_number', 'legacy_type', 'legacy_status',
                           'raw_payload', 'payload_hash', 'imported_at'])

    # Um SELECT por lote evita a criação de uma query por item.
    parent_ids = {}
    for chunk in _chunks(prepared.headers):
        parent_ids.update(LegacyMaterialRequest.objects.filter(
            legacy_id__in=[pk for pk, _ in chunk]
        ).values_list('legacy_id', 'id'))
    for chunk in _chunks(prepared.items):
        objects = [LegacyMaterialRequestItem(
            request_id=parent_ids[parent], legacy_item_id=item,
            raw_payload=row, payload_hash=_hash(row), imported_at=now,
        ) for parent, item, row in chunk]
        LegacyMaterialRequestItem.objects.bulk_create(objects, update_conflicts=True,
            unique_fields=['request', 'legacy_item_id'],
            update_fields=['raw_payload', 'payload_hash', 'imported_at'])
    for chunk in _chunks(prepared.issues):
        objects = [LegacyMaterialRequestIssue(identity=identity, reason=reason,
                   raw_payload=row, imported_at=now) for identity, reason, row in chunk]
        LegacyMaterialRequestIssue.objects.bulk_create(objects, update_conflicts=True,
            unique_fields=['identity'], update_fields=['reason', 'raw_payload', 'imported_at'])
    return prepared.counts
