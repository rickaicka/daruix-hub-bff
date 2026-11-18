"""Convites, contas de fornecedores e encerramento de leilões."""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.exceptions import ValidationError

from accounts.models import Supplier as PortalSupplier
from .models import Supplier, TenderBid, QuotationMap
from .quote_sync import merge_supplier_bid

logger = logging.getLogger(__name__)


def _site_url():
    return getattr(settings, "HUB_PUBLIC_URL", "http://localhost:4300").rstrip("/")


def _api_url():
    return getattr(settings, "HUB_API_PUBLIC_URL", _site_url()).rstrip("/")


def ensure_supplier_account(supplier):
    """Criar somente contas de fornecedor; nunca vincular conta de outro tipo pelo e-mail."""
    if supplier.portal_profile_id:
        profile = supplier.portal_profile
        if not profile.is_active or not profile.user.is_active or profile.user.user_type != "FORNECEDOR":
            raise ValidationError(f"Conta do fornecedor {supplier.name} está inativa ou inválida.")
        return profile.user
    email = supplier.email.strip().lower()
    if not email:
        raise ValidationError(f"Cadastre o e-mail do fornecedor {supplier.name} antes de publicar.")
    try:
        validate_email(email)
    except DjangoValidationError:
        raise ValidationError(f"E-mail inválido para o fornecedor {supplier.name}.")
    User = get_user_model()
    if User.objects.filter(email__iexact=email).exists():
        raise ValidationError(f"O e-mail de {supplier.name} já pertence a uma conta. Vincule o perfil no Cadastro de Fornecedores.")
    # Username estável e sem dados pessoais; senha criada exclusivamente pelo próprio fornecedor.
    user = User(username=f"fornecedor_mc_{supplier.pk}", name=supplier.name[:150],
                email=email, user_type="FORNECEDOR", is_active=True)
    user.set_unusable_password()
    user.save()
    profile = PortalSupplier.objects.create(user=user, legal_name=supplier.name[:180],
                                            trade_name=supplier.trade_name[:150] or None,
                                            document=supplier.document[:20] or None)
    supplier.portal_profile = profile
    supplier.save(update_fields=["portal_profile"])
    return user


def invite_selected(quotation):
    """Reservar as vagas exclusivamente para os fornecedores escolhidos, dentro da transação."""
    ids = [int(q["supplier"]["id"]) for q in quotation.quotes]
    if not 4 <= len(ids) <= 6 or len(ids) != len(set(ids)):
        raise ValidationError("Selecione de 4 a 6 fornecedores distintos antes de publicar.")
    suppliers = Supplier.objects.select_related("portal_profile__user").filter(pk__in=ids, active=True).in_bulk()
    if len(suppliers) != len(ids):
        raise ValidationError("Há fornecedor inativo ou inexistente na cotação.")
    recipients = []
    for supplier_id in ids:
        supplier = suppliers[supplier_id]
        user = ensure_supplier_account(supplier)
        if not user.email:
            raise ValidationError(f"O fornecedor {supplier.name} não possui e-mail válido.")
        TenderBid.objects.get_or_create(quotation=quotation, supplier=supplier)
        try:
            validate_email(supplier.email.strip())
        except DjangoValidationError:
            raise ValidationError(f"E-mail cadastrado inválido para {supplier.name}.")
        recipients.append((supplier.pk, supplier.name, user.pk, supplier.email.strip()))
    return recipients


def _send_bid_invitation(bid):
    """Gera nova senha/token e registra o resultado de envio; falha não vaza credenciais."""
    from .invite_access import create_credential
    import urllib.parse
    bid = TenderBid.objects.select_related("quotation", "supplier").get(pk=bid.pk)
    password, token = create_credential(bid)
    url = f"{_site_url()}/hub/obras/leilao-reverso?mapa={bid.quotation_id}&convite={urllib.parse.quote(token)}"
    message = (f"Olá, {bid.supplier.name}.\n\nConvite para cotar o mapa {bid.quotation.code}.\n"
               f"Usuário temporário: {bid.temp_username}\nSenha temporária: {password}\n"
               f"Link exclusivo: {url}\n"
               f"Expiração das credenciais: {timezone.localtime(bid.expires_at):%d/%m/%Y %H:%M}.\n"
               f"Prazo do mapa: {timezone.localtime(bid.quotation.tender_deadline):%d/%m/%Y %H:%M}.\n\n"
               "Você só poderá consultar os itens do mapa e sua própria proposta.\n")
    try:
        send_mail(f"Daruix Hub — Convite {bid.quotation.code}", message,
                  settings.DEFAULT_FROM_EMAIL, [bid.supplier.email], fail_silently=False)
    except Exception as exc:
        logger.exception("Erro no envio do convite %s", bid.pk)
        bid.email_error = f"{type(exc).__name__}: {str(exc)[:300]}"
        bid.save(update_fields=["email_error"])
        return False
    bid.emailed_at = timezone.now()
    bid.save(update_fields=["emailed_at"])
    return True


def resend_invitation(bid_id):
    bid = TenderBid.objects.select_related("quotation", "supplier").get(pk=bid_id)
    from .invite_access import is_valid
    quotation = bid.quotation
    if (not quotation.tender_opened_at or quotation.tender_closed_at or
            quotation.tender_deadline is None or quotation.tender_deadline <= timezone.now()):
        return False
    if not bid.supplier.active:
        return False
    return _send_bid_invitation(bid)


def send_invitations(quotation_id, recipients):
    for supplier_id, _, _, _ in recipients:
        bid = TenderBid.objects.get(quotation_id=quotation_id, supplier_id=supplier_id)
        _send_bid_invitation(bid)


def close_expired_tender(quotation):
    """Idempotente; chamar sob select_for_update para evitar perda de propostas."""
    if (quotation.tender_opened_at is None or quotation.tender_closed_at is not None
            or quotation.status != QuotationMap.Status.DRAFT
            or quotation.tender_deadline is None or quotation.tender_deadline > timezone.now()):
        return False
    for bid in quotation.tender_bids.filter(submitted_at__isnull=False).exclude(offer__isnull=True).order_by("pk"):
        # Reconciliar ofertas antigas sem sobrescrever ajustes manuais.
        merge_supplier_bid(quotation, bid)
    quotation.tender_closed_at = timezone.now()
    quotation.version += 1
    quotation.save(update_fields=["quotes", "tender_closed_at", "version"])
    return True


def close_expired_tenders(ids=None):
    filters = Q(tender_opened_at__isnull=False, tender_closed_at__isnull=True,
                tender_deadline__lte=timezone.now(), status=QuotationMap.Status.DRAFT)
    if ids is not None:
        filters &= Q(pk__in=ids)
    total = 0
    # Locks independentes: um mapa com erro não impede os demais.
    for pk in QuotationMap.objects.filter(filters).values_list("pk", flat=True).iterator():
        with transaction.atomic():
            quotation = QuotationMap.objects.select_for_update().get(pk=pk)
            total += int(close_expired_tender(quotation))
    return total
