"""Serviço compartilhado para notificações internas do Daruix Hub.

Chamar publish() dentro de transaction.on_commit() quando o evento depende
exclusivamente de uma mutação concluída. Nunca confiar no route/payload para
conceder acesso: a funcionalidade de destino deve revalidar permissões.
"""
from django.db import transaction
from django.utils import timezone
from accounts.models import HubNotification


def publish(*, event, module, recipients, title, message='', route='',
            resource_type='', resource_id='', payload=None, actor=None, key=None):
    """Cria/atualiza uma notificação por destinatário e chave idempotente.

    Recebe usuários ou IDs. Não cria registros para usuários inativos;
    retorna a lista de notificações criadas/atualizadas.
    """
    if not event or not module or not resource_type or resource_id is None or resource_id == '':
        raise ValueError('module, event, resource_type e resource_id são obrigatórios')
    if payload is not None and not isinstance(payload, dict):
        raise ValueError('payload deve ser um objeto JSON')
    from django.contrib.auth import get_user_model
    ids = {getattr(user, 'pk', user) for user in recipients}
    ids.discard(None)
    if not ids:
        return []
    idempotency_key = key or f'{module}:{event}:{resource_type}:{resource_id}'
    if len(idempotency_key) > 160:
        raise ValueError('key excede 160 caracteres')
    actor_id = getattr(actor, 'pk', actor) if actor is not None else None
    users = get_user_model().objects.filter(pk__in=ids, is_active=True)
    result = []
    with transaction.atomic():
        for user in users:
            notification, _ = HubNotification.objects.update_or_create(
                recipient=user, key=idempotency_key,
                defaults=dict(actor_id=actor_id, kind=event[:48], event=event,
                    module=module, title=title, message=message, route=route,
                    resource_type=resource_type, resource_id=str(resource_id),
                    payload=payload or {}, read_at=None, resolved_at=None),
            )
            result.append(notification)
    return result


def resolve(*, module, event=None, resource_type=None, resource_id=None,
            recipients=None, key_prefix=None):
    """Encerra notificações ativas, sem apagá-las do histórico."""
    queryset = HubNotification.objects.filter(module=module, resolved_at__isnull=True)
    if event is not None:
        queryset = queryset.filter(event=event)
    if resource_type is not None:
        queryset = queryset.filter(resource_type=resource_type)
    if resource_id is not None:
        queryset = queryset.filter(resource_id=str(resource_id))
    if key_prefix is not None:
        queryset = queryset.filter(key__startswith=key_prefix)
    if recipients is not None:
        ids = {getattr(user, 'pk', user) for user in recipients}
        queryset = queryset.filter(recipient_id__in=ids)
    if not any(value is not None for value in (event, resource_type, resource_id, recipients, key_prefix)):
        raise ValueError('Informe pelo menos um filtro além do módulo para resolver notificações')
    return queryset.update(resolved_at=timezone.now())
