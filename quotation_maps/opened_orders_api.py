"""Lista unificada de OCs, autenticada no Django Hub.

Legado continua sendo a fonte das OCs antigas. O Hub fornece OCs geradas
pelo Mapa de Cotação. Não publica o token servidor-servidor no navegador.
"""
from datetime import timezone as dt_timezone
import logging

import json
from urllib.request import urlopen
from urllib.error import HTTPError, URLError
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from accounts.services.permission_service import user_has_permission

from .models import PurchaseOrder

logger = logging.getLogger(__name__)


def _legacy_rows():
    base = getattr(settings, 'ORDERS_LEGACY_API_URL', '').rstrip('/')
    if not base:
        raise ValueError('ORDERS_LEGACY_API_URL não configurada')
    with urlopen(f'{base}/opened-buy-order', timeout=20) as response:
        payload = json.load(response)
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and payload.get('status') != 'error':
        rows = payload.get('data')
    else:
        raise ValueError('Erro declarado pelo legado')
    if not isinstance(rows, list):
        raise ValueError('Formato inesperado da lista legada')
    return [dict(row, source='legacy', pdf_available=True) for row in rows if isinstance(row, dict)]


def _hub_rows():
    qs = PurchaseOrder.objects.select_related('quotation_map__requisition__proposal').order_by('-created_at', '-id')
    result = []
    for order in qs.iterator():
        proposal = order.quotation_map.requisition.proposal
        snapshot = order.supplier_snapshot or {}
        name = (snapshot.get('name') or snapshot.get('trade_name') or '') if isinstance(snapshot, dict) else str(snapshot)
        result.append({
            'source': 'hub',
            'pdf_available': False,
            'pc_number': proposal.code,
            'cod': order.code.removeprefix('OC'),
            'code': order.code,
            'dt_solicitation': order.created_at.astimezone(dt_timezone.utc).strftime('%d/%m/%Y'),
            'dt_delivery': order.promised_delivery_at.strftime('%d/%m/%Y') if order.promised_delivery_at else '',
            'buy_order_value': str(order.total),
            'supplier': name,
            'description': f'Mapa de Cotação {order.quotation_map.code}',
            'status': 'Gerada',
            'status_label': 'Gerada',
        })
    return result


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def opened_purchase_orders(request):
    """Somente usuários autenticados; sem endpoint público com preços do Hub."""
    if not user_has_permission(request.user, 'opened_order.view'):
        return Response({'detail': 'Permissão insuficiente.'}, status=403)
    try:
        legacy = _legacy_rows()
    except (HTTPError, URLError, OSError, ValueError, TypeError) as exc:
        logger.warning('Falha na leitura de OCs legadas: %s', type(exc).__name__)
        return Response({'detail': 'Não foi possível consultar as OCs legadas.'}, status=502)
    hub = _hub_rows()
    seen = set()
    merged = []
    for row in (*legacy, *hub):
        pc = str(row.get('pc_number') or '').strip()
        number = str(row.get('cod') or '').removeprefix('OC').strip()
        key = (pc.upper(), number)
        if key in seen:
            logger.error('Código de OC duplicado entre Hub e legado: %s', key)
            return Response({'detail': 'Numeração de OC duplicada entre as origens. Contate o administrador.'}, status=409)
        seen.add(key)
        merged.append(row)
    return Response({'status': 'success', 'data': merged, 'pagination': {'total': len(merged), 'page': 1, 'per_page': len(merged)}})
