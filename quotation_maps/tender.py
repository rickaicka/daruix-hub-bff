from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import QuotationMap, Supplier, TenderBid
from .serializers import TenderBidWrite
from .views import Conflict, Pagination, validate_quotes
from .invitations import close_expired_tenders
from .invite_access import InvitationAuthentication, InvitationOnly
from .quote_sync import merge_supplier_bid


def supplier_for(user):
    if not user.is_authenticated or not user.is_active or user.user_type != "FORNECEDOR":
        raise PermissionDenied("Acesso exclusivo de fornecedores vinculados.")
    supplier = Supplier.objects.filter(active=True, portal_profile__user=user, portal_profile__is_active=True).first()
    if supplier is None:
        raise PermissionDenied("Sua conta precisa estar vinculada ao cadastro de fornecedor.")
    return supplier


class TenderView(viewsets.GenericViewSet):
    authentication_classes = [InvitationAuthentication]
    permission_classes = [InvitationOnly]
    pagination_class = Pagination
    lookup_value_regex = r"[0-9]+"
    serializer_class = TenderBidWrite

    def _visible(self, supplier):
        # Nenhum fornecedor pode entrar em leilões para os quais não foi convidado.
        # O token de cada convite autoriza exclusivamente o mapa correspondente.
        return QuotationMap.objects.filter(
            pk=self.request.auth.quotation_id,
            tender_bids__supplier=supplier,
            tender_bids__expires_at__gt=timezone.now(),
            tender_bids__revoked_at__isnull=True,
        ).distinct().select_related(
            "requisition__proposal", "approved_revision"
        ).order_by("-tender_opened_at", "-pk")

    def _header(self, quotation):
        rev = quotation.approved_revision
        return dict(id=quotation.pk, code=quotation.code, pc=quotation.requisition.proposal.code,
                    reference_date=rev.reference_date, delivery_date=rev.delivery_date,
                    deadline=quotation.tender_deadline,
                    open=quotation.status == QuotationMap.Status.DRAFT and
                         quotation.tender_closed_at is None and quotation.tender_deadline is not None and quotation.tender_deadline > timezone.now())

    def _detail(self, quotation, supplier):
        participation = quotation.tender_bids.filter(supplier=supplier).first()
        items = [
            {key: item[key] for key in ("id", "description", "unit", "quantity", "period", "period_unit")}
            for item in quotation.items
        ]
        own_offer = None
        if participation and participation.offer:
            own_offer = {key: value for key, value in participation.offer.items() if key != "supplier"}
        return dict(self._header(quotation), items=items, participating=participation is not None,
                    own_offer=own_offer)

    def list(self, request):
        supplier = supplier_for(request.user)
        close_expired_tenders()
        page = self.paginate_queryset(self._visible(supplier))
        return self.get_paginated_response([self._header(quotation) for quotation in page])

    def retrieve(self, request, pk=None):
        supplier = supplier_for(request.user)
        close_expired_tenders()
        return Response(self._detail(get_object_or_404(self._visible(supplier), pk=pk), supplier))

    def _lock(self, pk, supplier):
        reference = get_object_or_404(self._visible(supplier), pk=pk)
        quotation = QuotationMap.objects.select_for_update().get(pk=reference.pk)
        if not self._header(quotation)["open"]:
            raise Conflict("A cotação está fechada para propostas.")
        return quotation

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def participate(self, request, pk=None):
        supplier = supplier_for(request.user)
        quotation = self._lock(pk, supplier)
        # Convite é criado pelo comprador na publicação; não há vagas públicas.
        if not quotation.tender_bids.filter(supplier=supplier).exists():
            raise PermissionDenied("Este fornecedor não foi convidado para o leilão.")
        return Response(self._detail(quotation, supplier))

    @action(detail=True, methods=["put"])
    @transaction.atomic
    def bid(self, request, pk=None):
        supplier = supplier_for(request.user)
        quotation = self._lock(pk, supplier)
        participation = quotation.tender_bids.filter(supplier=supplier).first()
        if participation is None:
            raise ValidationError("Confirme sua participação antes de enviar uma proposta.")
        serializer = TenderBidWrite(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data, supplier_id=supplier.pk)
        if data.get("quoted_on") is None:
            data["quoted_on"] = timezone.localdate()
        data["offers"] = [dict(offer, available_quantity=None, brand="", selected=False)
                          for offer in data["offers"] if offer["unit_price"] is not None]
        if not data["offers"]:
            raise ValidationError("Informe um preço unitário para pelo menos um item.")
        participation.offer = validate_quotes(quotation, [data])[0]
        participation.submitted_at = timezone.now()
        participation.save(update_fields=["offer", "submitted_at"])
        if merge_supplier_bid(quotation, participation):
            quotation.version += 1
            quotation.save(update_fields=["quotes", "version"])
        return Response(self._detail(quotation, supplier))
