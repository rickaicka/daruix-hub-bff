"""E-mails de agradecimento a participantes sem OC, disparados somente após commit."""
import logging
import re

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from .models import PurchaseOrder, TenderBid, TenderOutcomeNotification

logger = logging.getLogger(__name__)


def prepare_outcome_notifications(quotation):
    """Chamar na transação que criou as OCs. Retorna ids novos, sem enviar mensagens."""
    awarded_ids = set(PurchaseOrder.objects.filter(quotation_map=quotation).values_list("supplier_id", flat=True))
    # Somente quem enviou proposta efetiva, não apenas quem recebeu convite.
    submitted = (TenderBid.objects.filter(quotation=quotation, submitted_at__isnull=False)
                 .exclude(offer__isnull=True).select_related("supplier"))
    ids = []
    for bid in submitted:
        if bid.supplier_id in awarded_ids:
            continue
        email = bid.supplier.email.strip()
        notification, created = TenderOutcomeNotification.objects.get_or_create(
            quotation=quotation, supplier=bid.supplier,
            defaults={"recipient_email": email},
        )
        if created:
            ids.append(notification.pk)
    return ids


def dispatch_outcome_notifications(notification_ids):
    """Erro de SMTP nunca desfaz OCs já gravadas. Cada envio tem estado rastreável."""
    for notification_id in notification_ids:
        with transaction.atomic():
            notice = (TenderOutcomeNotification.objects.select_for_update()
                      .select_related("quotation__requisition__proposal", "supplier")
                      .get(pk=notification_id))
            if notice.status not in (notice.Status.PENDING, notice.Status.FAILED):
                continue
            # Proteção adicional: não notificar se houver OC para este fornecedor.
            if PurchaseOrder.objects.filter(quotation_map=notice.quotation, supplier=notice.supplier).exists():
                continue
            notice.status = notice.Status.SENDING
            notice.error = ""
            notice.save(update_fields=["status", "error"])
        try:
            quotation = notice.quotation
            map_number = re.sub(r"^MC", "", quotation.code, flags=re.I)
            pc = quotation.requisition.proposal.code
            context = {"supplier_name": notice.supplier.name, "map_number": map_number, "pc": pc}
            body = (
                f"Olá, {notice.supplier.name}!\n\n"
                f"Agradecemos sua participação no Mapa de Concorrência nº {map_number}, referente à {pc}.\n\n"
                "Após analisarmos cuidadosamente as propostas, informamos que, nesta oportunidade, "
                "os itens foram direcionados a outras propostas que melhor atenderam às necessidades desta contratação.\n\n"
                "Valorizamos o tempo e a dedicação da sua equipe e esperamos contar com sua empresa "
                "em futuras oportunidades de fornecimento e parceria.\n\n"
                "Muito obrigado pela participação e confiança!\n\n"
                "Atenciosamente,\nEquipe de Compras | SGO Web - Daruix Engenharia\n"
            )
            email = EmailMultiAlternatives(
                subject=f"SGO Web | Agradecimento pela participação na cotação {map_number}",
                body=body, from_email=settings.DEFAULT_FROM_EMAIL, to=[notice.recipient_email],
            )
            email.attach_alternative(render_to_string("quotation_maps/outcome_email.html", context), "text/html")
            email.send(fail_silently=False)
        except Exception as exc:
            logger.exception("Falha ao enviar agradecimento do mapa %s ao fornecedor %s", notice.quotation_id, notice.supplier_id)
            TenderOutcomeNotification.objects.filter(pk=notification_id).update(
                status=TenderOutcomeNotification.Status.FAILED, error=f"{type(exc).__name__}: {str(exc)[:500]}")
        else:
            TenderOutcomeNotification.objects.filter(pk=notification_id).update(
                status=TenderOutcomeNotification.Status.SENT, sent_at=timezone.now(), error="")
