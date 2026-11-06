"""Adaptador dos eventos da RM para o serviço genérico do Hub."""
from django.contrib.auth import get_user_model
from django.db import transaction
from accounts.services.notifications import publish, resolve
from material_requisitions.services.requisitions import can_decide_rm


def after_decision(rev, actor, action):
    revision_id, actor_id = rev.pk, actor.pk
    transaction.on_commit(lambda: _deliver(revision_id, actor_id, action))


def _deliver(revision_id, actor_id, action):
    from material_requisitions.models import MaterialRequisitionRevision
    rev = MaterialRequisitionRevision.objects.select_related('requisition', 'owner', 'requisition__proposal').get(pk=revision_id)
    model = get_user_model()
    resource_id = rev.requisition_id
    if action in ('approve', 'reject', 'cancel'):
        resolve(module='obras', event='rm.submitted', resource_type='material_requisition', resource_id=resource_id)
        # Compatibilidade com notificações criadas pela versão anterior.
        from accounts.models import HubNotification
        from django.utils import timezone
        HubNotification.objects.filter(kind='RM_APPROVAL', key__startswith=f'rm:{resource_id}:', resolved_at__isnull=True).update(resolved_at=timezone.now())
    if action == 'submit':
        # Mesma regra do endpoint de decisão: RT da Proposta + DIRETORIA
        # (somente COLABORADOR), todos com permissão e sem autoaprovação.
        from django.db.models import Q
        technical_id = rev.requisition.proposal.technical_responsible_id
        candidates = model.objects.filter(is_active=True).filter(
            Q(pk=technical_id) |
            Q(user_type='COLABORADOR', group__is_active=True, group__name__iexact='diretoria')
        ).select_related('group').distinct()
        recipients = [candidate for candidate in candidates if can_decide_rm(rev, candidate)]
        event, title = 'rm.submitted', 'RM aguardando sua aprovação'
    elif action in ('approve', 'reject'):
        recipients = list(model.objects.filter(pk__in={rev.owner_id, rev.requisition.requester_id}).exclude(pk=actor_id))
        event = f'rm.{action}'
        title = 'RM aprovada' if action == 'approve' else 'RM reprovada'
    else:
        return
    publish(module='obras', event=event, recipients=recipients,
            title=title, message=rev.requisition.number,
            route='/hub/obras/requisicao-materiais', resource_type='material_requisition',
            resource_id=resource_id, payload={'revision_id': revision_id},
            actor=actor_id, key=f'rm:{resource_id}:{revision_id}:{action}')
