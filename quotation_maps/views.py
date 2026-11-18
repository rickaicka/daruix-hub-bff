from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from .models import PurchaseOrder, QuotationMap, Supplier
from .serializers import MapRead, MapSummary, MapWrite, SupplierRead, SupplierWrite, TenderPublish, VersionWrite
from .services import can_manage, resolve_ready
from .quote_sync import merge_buyer_quotes
from .invitations import invite_selected, send_invitations, close_expired_tenders, close_expired_tender, resend_invitation


Status = QuotationMap.Status


class ManageQuotations(BasePermission):
    def has_permission(self, request, view):
        return can_manage(request.user)


class Pagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class Conflict(APIException):
    status_code = 409
    default_detail = "O mapa foi alterado. Reabra o mapa antes de continuar."


class SupplierView(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [ManageQuotations]
    serializer_class = SupplierRead
    pagination_class = Pagination

    def get_queryset(self):
        search = self.request.query_params.get("search", "").strip()
        return Supplier.objects.filter(active=True).filter(
            Q(name__icontains=search) | Q(trade_name__icontains=search) | Q(document__icontains=search) | Q(contact__icontains=search)
        ).order_by("name", "pk")


class SupplierRegistryView(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                           mixins.UpdateModelMixin, viewsets.GenericViewSet):
    permission_classes = [ManageQuotations]
    serializer_class = SupplierWrite
    pagination_class = Pagination

    def get_queryset(self):
        search = self.request.query_params.get("search", "").strip()
        return Supplier.objects.filter(
            Q(name__icontains=search) | Q(trade_name__icontains=search) | Q(document__icontains=search) | Q(contact__icontains=search)
        ).order_by("name", "pk")

    @action(detail=False, methods=["get"], url_path="portal-profiles")
    def portal_profiles(self, request):
        from accounts.models import Supplier as PortalProfile
        search = request.query_params.get("search", "").strip()
        profiles = PortalProfile.objects.filter(is_active=True, user__is_active=True, user__user_type="FORNECEDOR")
        profiles = profiles.filter(
            Q(legal_name__icontains=search) | Q(trade_name__icontains=search) |
            Q(user__name__icontains=search) | Q(document__icontains=search)
        ).select_related("user", "quotation_supplier").order_by("pk")
        page = self.paginate_queryset(profiles)
        return self.get_paginated_response([dict(id=row.pk, name=str(row), document=row.document,
                                                 linked_supplier=row.quotation_supplier.pk
                                                 if hasattr(row, "quotation_supplier") else None) for row in page])


def price_for(item, offer):
    return (Decimal(item["quantity"]) * Decimal(offer["unit_price"]) *
            (item["period"] or 1)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def validate_quotes(quotation, quotes):
    items = {item["id"]: item for item in quotation.items}
    supplier_ids = [quote["supplier_id"] for quote in quotes]
    if len(supplier_ids) != len(set(supplier_ids)):
        raise ValidationError("Cada fornecedor pode aparecer uma única vez.")
    previous = {quote["supplier"]["id"]: quote["supplier"] for quote in quotation.quotes}
    suppliers = Supplier.objects.filter(Q(active=True) | Q(pk__in=previous)).in_bulk(supplier_ids)
    selected_items = set()
    normalized = []
    for quote in quotes:
        supplier = suppliers.get(quote["supplier_id"])
        if supplier is None:
            raise ValidationError("Fornecedor inválido ou inativo.")
        supplier_snapshot = dict(previous.get(supplier.pk) or SupplierRead(supplier).data)
        supplier_snapshot.update({field: quote[field] for field in ("contact", "phone", "email") if field in quote})
        offers = []
        seen = set()
        for offer in quote["offers"]:
            item_id = offer["item_id"]
            item = items.get(item_id)
            if item is None or item_id in seen:
                raise ValidationError("Item duplicado ou fora da RM aprovada.")
            seen.add(item_id)
            price, available = offer["unit_price"], offer["available_quantity"]
            if offer["selected"]:
                if item_id in selected_items or price is None:
                    raise ValidationError("Escolha uma oferta com preço por item.")
                if available is not None and available < Decimal(item["quantity"]):
                    raise ValidationError(f"Quantidade insuficiente para {item['description']}.")
                selected_items.add(item_id)
            offers.append(dict(offer, unit_price=str(price) if price is not None else None,
                               available_quantity=str(available) if available is not None else None))
        terms = {key: quote[key] for key in ("payment", "delivery", "notes")}
        # Novos fornecedores: usar as condições do cadastro como padrão.
        # Em mapas já existentes, preservar exatamente os valores recebidos,
        # inclusive campos intencionalmente apagados pelo comprador.
        if supplier.pk not in previous:
            terms["payment"] = terms["payment"] or supplier.payment_terms[:255]
            terms["delivery"] = terms["delivery"] or supplier.delivery_terms[:255]
        terms.update(quoted_on=quote["quoted_on"].isoformat() if quote["quoted_on"] else None,
                     freight=str(quote["freight"]), discount=str(quote["discount"]))
        normalized.append(dict(supplier=supplier_snapshot, offers=offers, **terms))
    return normalized


def order_data(quotation):
    items = {item["id"]: item for item in quotation.items}
    for quote in quotation.quotes:
        lines = [
            dict(items[offer["item_id"]], unit_price=offer["unit_price"], brand=offer["brand"],
                 quote_notes=offer["notes"], total=str(price_for(items[offer["item_id"]], offer)))
            for offer in quote["offers"] if offer["selected"]
        ]
        if not lines:
            continue
        terms = {key: value for key, value in quote.items() if key not in ("supplier", "offers", "validity")}
        total = sum(Decimal(line["total"]) for line in lines) + Decimal(terms["freight"]) - Decimal(terms["discount"])
        if total < 0:
            raise ValidationError(f"Desconto superior ao total de {quote['supplier']['name']}.")
        yield dict(supplier_id=quote["supplier"]["id"], supplier_snapshot=quote["supplier"],
                   lines=lines, terms=terms, total=total)


class MapView(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [ManageQuotations]
    pagination_class = Pagination
    lookup_value_regex = r"[0-9]+"

    def get_serializer_class(self):
        return MapSummary if self.action == "list" else MapRead

    def get_queryset(self):
        close_expired_tenders()
        queryset = QuotationMap.objects.select_related("requisition__proposal")
        if self.action != "list":
            return queryset.prefetch_related("orders")
        params = self.request.query_params
        fields = {"code": "code", "pc": "requisition__proposal__code",
                  "rm": "requisition__number", "work": "requisition__proposal__work_name"}
        if search := params.get("search", "").strip():
            query = Q()
            for field in fields.values():
                query |= Q(**{f"{field}__icontains": search})
            queryset = queryset.filter(query)
        for key, field in fields.items():
            if value := params.get(key, "").strip():
                queryset = queryset.filter(**{f"{field}__icontains": value})
        if status := params.get("status"):
            queryset = queryset.filter(status=status)
        return queryset.order_by("-created_at", "-pk")

    def _locked(self, pk, request, serializer=VersionWrite, *, allow_ordered=False):
        data = serializer(data=request.data)
        data.is_valid(raise_exception=True)
        # Mesmo lock da RM antes de travar o mapa. Evita corrida com cancelamento.
        from material_requisitions.models import MaterialRequisition
        reference = get_object_or_404(QuotationMap.objects.only("requisition_id"), pk=pk)
        rm = MaterialRequisition.objects.select_for_update().get(pk=reference.requisition_id)
        quotation = QuotationMap.objects.select_for_update().get(pk=pk)
        close_expired_tender(quotation)
        if allow_ordered and quotation.status == Status.ORDERED:
            return quotation, data.validated_data
        if quotation.version != data.validated_data["version"]:
            raise Conflict()
        if rm.cancelled_at or rm.approved_revision_id != quotation.approved_revision_id:
            raise Conflict("A RM de origem precisa estar aprovada.")
        return quotation, data.validated_data

    def _save(self, quotation, status):
        quotation.status = status
        quotation.version += 1
        quotation.save(update_fields=["status", "version", "quotes", "notes", "tender_opened_at", "tender_closed_at", "tender_deadline"])
        return Response(MapRead(quotation).data)

    @transaction.atomic
    def partial_update(self, request, pk=None):
        quotation, data = self._locked(pk, request, MapWrite)
        if quotation.status not in (Status.READY, Status.DRAFT):
            raise Conflict("O mapa já foi encerrado.")
        if quotation.tender_opened_at and not quotation.tender_closed_at:
            before = {int(q["supplier"]["id"]) for q in quotation.quotes}
            after = {int(q["supplier_id"]) for q in data["quotes"]}
            if before != after:
                raise Conflict("Não é possível adicionar ou remover fornecedores durante o leilão.")
        quotation.quotes = merge_buyer_quotes(quotation, validate_quotes(quotation, data["quotes"]))
        quotation.notes = data["notes"]
        if quotation.buyer_id is None:
            quotation.buyer = request.user
            quotation.save(update_fields=["buyer"])
        resolve_ready(quotation.pk)
        return self._save(quotation, Status.DRAFT)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def finalize(self, request, pk=None):
        quotation, _ = self._locked(pk, request)
        if quotation.status != Status.DRAFT:
            raise Conflict("Salve a cotação antes de finalizar.")
        if quotation.tender_opened_at and not quotation.tender_closed_at:
            raise Conflict("Encerre o leilão reverso antes de finalizar.")
        if not 4 <= len(quotation.quotes) <= 6:
            raise ValidationError("Selecione de 4 a 6 fornecedores para finalizar.")
        chosen = {offer["item_id"] for quote in quotation.quotes for offer in quote["offers"] if offer["selected"]}
        if chosen != {item["id"] for item in quotation.items} or not chosen:
            raise ValidationError("Escolha um fornecedor para cada item da RM.")
        list(order_data(quotation))
        return self._save(quotation, Status.FINAL)

    @action(detail=True, methods=["post"], url_path="publish-tender")
    @transaction.atomic
    def publish_tender(self, request, pk=None):
        quotation, data = self._locked(pk, request, TenderPublish)
        if quotation.status not in (Status.READY, Status.DRAFT) or quotation.tender_opened_at:
            raise Conflict("Este mapa não pode abrir outro leilão.")
        recipients = invite_selected(quotation)
        quotation.tender_opened_at = timezone.now()
        quotation.buyer = request.user
        quotation.tender_deadline = data["deadline"]
        resolve_ready(quotation.pk)
        response = self._save(quotation, Status.DRAFT)
        quotation.save(update_fields=["buyer"])
        transaction.on_commit(lambda: send_invitations(quotation.pk, recipients))
        return response

    @action(detail=True, methods=["post"], url_path="resend-invitation")
    @transaction.atomic
    def resend_invitation(self, request, pk=None):
        quotation, data = self._locked(pk, request)
        if not quotation.tender_opened_at or quotation.tender_closed_at or quotation.tender_deadline <= timezone.now():
            raise Conflict("Não é possível reenviar convites para leilão encerrado.")
        try:
            supplier_id = int(request.data["supplier_id"])
        except (KeyError, ValueError, TypeError):
            raise ValidationError({"supplier_id": "Informe um fornecedor convidado."})
        bid = quotation.tender_bids.filter(supplier_id=supplier_id).first()
        if bid is None:
            raise ValidationError("Fornecedor não convidado para este mapa.")
        transaction.on_commit(lambda: resend_invitation(bid.pk))
        return Response({"detail": "Reenvio solicitado. Confira o status de envio do convite."}, status=202)

    @action(detail=True, methods=["post"], url_path="close-tender")
    @transaction.atomic
    def close_tender(self, request, pk=None):
        quotation, _ = self._locked(pk, request)
        if quotation.status != Status.DRAFT or not quotation.tender_opened_at or quotation.tender_closed_at:
            raise Conflict("Este mapa não tem leilão aguardando encerramento.")
        # Encerramento antecipado não é permitido: preserva o prazo informado aos fornecedores.
        if quotation.tender_deadline > timezone.now():
            raise Conflict("O leilão ainda está dentro do prazo informado aos fornecedores.")
        close_expired_tender(quotation)
        return Response(MapRead(quotation).data)

    @action(detail=True, methods=["post"], url_path="generate-orders")
    @transaction.atomic
    def generate_orders(self, request, pk=None):
        quotation, _ = self._locked(pk, request, allow_ordered=True)
        if quotation.status == Status.ORDERED:
            return Response(MapRead(quotation).data)
        if quotation.status != Status.FINAL:
            raise Conflict("Finalize o mapa antes de gerar ordens de compra.")
        from commercial.models import Proposal
        # Serializa a sequência de uma mesma PC mesmo entre mapas distintos.
        proposal = Proposal.objects.select_for_update().get(pk=quotation.requisition.proposal_id)
        from .order_numbering import make_order_code, legacy_last_sequence
        # A transação mantém lock da PC e serializa a emissão concorrente.
        # O marco legado precisa considerar TODAS as OCs, não apenas abertas.
        try:
            sequence = legacy_last_sequence(proposal.code)
        except ValueError as exc:
            raise Conflict(str(exc)) from exc
        existing = list(PurchaseOrder.objects.filter(
            quotation_map__requisition__proposal=proposal
        ).values_list('code', flat=True))
        prefix = f'OC{proposal.code.removeprefix("PC")}'
        numbers = [int(code[len(prefix):]) for code in existing
                   if code and code.startswith(prefix) and len(code) == len(prefix) + 3
                   and code[len(prefix):].isdigit()]
        sequence = max([sequence, *numbers])
        orders = []
        for data in order_data(quotation):
            sequence += 1
            try:
                code = make_order_code(proposal.code, sequence)
            except ValueError as exc:
                raise Conflict(str(exc)) from exc
            orders.append(PurchaseOrder(
                quotation_map=quotation, code=code, **data
            ))
        PurchaseOrder.objects.bulk_create(orders)
        return self._save(quotation, Status.ORDERED)


class PurchaseOrderDeliveryView(viewsets.GenericViewSet):
    """Registro de datas reais para pontuação de pontualidade: somente Compras."""
    permission_classes = [ManageQuotations]
    lookup_value_regex = r"[0-9]+"

    @action(detail=True, methods=["patch"], url_path="delivery")
    @transaction.atomic
    def delivery(self, request, pk=None):
        from rest_framework import serializers

        class DeliveryDates(serializers.Serializer):
            promised_delivery_at = serializers.DateField(allow_null=True, required=False)
            delivered_at = serializers.DateField(allow_null=True, required=False)

        form = DeliveryDates(data=request.data)
        form.is_valid(raise_exception=True)
        order = get_object_or_404(PurchaseOrder.objects.select_for_update(), pk=pk)
        for field, value in form.validated_data.items():
            setattr(order, field, value)
        if not form.validated_data:
            raise ValidationError("Informe pelo menos uma data de entrega.")
        order.save(update_fields=list(form.validated_data))
        return Response({"id": order.pk,
                         "promised_delivery_at": order.promised_delivery_at,
                         "delivered_at": order.delivered_at})
