from django.http import HttpResponse
from django.db import transaction
from memorando_remessas.models.nota_fiscal import ShipmentMemoInvoice
from memorando_remessas.serializers.nota_fiscal import InvoiceSerializer, InvoiceBatchSerializer
from memorando_remessas.services.nota_fiscal_reader import read_invoice
from memorando_remessas.services.memorando_pdf_service import generate_shipment_memo_pdf
from django.db.models import Prefetch
from defusedxml import ElementTree as ET
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.filters import (
    OrderingFilter,
    SearchFilter,
)
from rest_framework.parsers import (
    FormParser,
    MultiPartParser,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from memorando_remessas.filters import ShipmentMemoFilter
from memorando_remessas.models import (
    ShipmentMemo,
    ShipmentMemoOption,
    ShipmentMemoResponsible,
)
from memorando_remessas.pagination import (
    ShipmentMemoPagination,
)
from memorando_remessas.permissions import (
    HasShipmentMemoCancelPermission,
    HasShipmentMemoCreatePermission,
    HasShipmentMemoDeletePermission,
    HasShipmentMemoSendPermission,
    HasShipmentMemoUpdatePermission,
    HasShipmentMemoViewPermission,
)
from memorando_remessas.serializers import (
    ShipmentMemoCancelSerializer,
    ShipmentMemoHistorySerializer,
    ShipmentMemoListSerializer,
    ShipmentMemoRevisionSerializer,
    ShipmentMemoSendSerializer,
    ShipmentMemoSerializer,
)
from memorando_remessas.services import (
    cancel_shipment_memo,
    create_shipment_memo_revision,
    delete_shipment_memo,
    send_shipment_memo,
)


@extend_schema_view(
    list=extend_schema(
        tags=["memorando-remessas/memorandos"],
        summary="Listar memorandos de remessa",
    ),
    retrieve=extend_schema(
        tags=["memorando-remessas/memorandos"],
        summary="Detalhar memorando de remessa",
    ),
    create=extend_schema(
        tags=["memorando-remessas/memorandos"],
        summary="Criar memorando de remessa",
    ),
    update=extend_schema(
        tags=["memorando-remessas/memorandos"],
        summary="Atualizar memorando de remessa",
    ),
    partial_update=extend_schema(
        tags=["memorando-remessas/memorandos"],
        summary="Atualizar parcialmente memorando",
    ),
    destroy=extend_schema(
        tags=["memorando-remessas/memorandos"],
        summary="Excluir memorando em rascunho",
    ),
)
class ShipmentMemoViewSet(ModelViewSet):
    serializer_class = ShipmentMemoSerializer
    pagination_class = ShipmentMemoPagination

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_class = ShipmentMemoFilter

    search_fields = [
        "code",
        "cost_center",
        "work_name",
        "client_name",
        "client_document",
        "subject",
        "attention_to",
        "responsible_links__user__name",
        "responsible_links__user__username",
        "responsible_links__user__email",
    ]

    ordering_fields = [
        "id",
        "code",
        "revision",
        "status",
        "shipping_date",
        "work_name",
        "client_name",
        "cost_center",
        "created_at",
        "updated_at",
    ]

    ordering = [
        "-created_at",
    ]

    def get_queryset(self):
        responsible_queryset = (
            ShipmentMemoResponsible.objects
            .select_related(
                "user",
                "added_by",
            )
            .order_by(
                "-is_primary",
                "created_at",
                "id",
            )
        )

        option_queryset = (
            ShipmentMemoOption.objects
            .order_by(
                "option_type",
                "order",
                "name",
                "id",
            )
        )

        return (
            ShipmentMemo.objects
            .select_related(
                "revised_from",
                "created_by",
                "updated_by",
                "sent_by",
                "cancelled_by",
            )
            .prefetch_related(
                Prefetch(
                    "responsible_links",
                    queryset=responsible_queryset,
                ),
                Prefetch(
                    "options",
                    queryset=option_queryset,
                ),
            )
            .all()
            .distinct()
        )

    def get_serializer_class(self):
        if self.action == "list":
            return ShipmentMemoListSerializer

        if self.action == "send_memo":
            return ShipmentMemoSendSerializer

        if self.action == "cancel_memo":
            return ShipmentMemoCancelSerializer

        if self.action == "create_revision":
            return ShipmentMemoRevisionSerializer

        if self.action == "history":
            return ShipmentMemoHistorySerializer

        return ShipmentMemoSerializer

    def get_permissions(self):
        permission_classes = [
            IsAuthenticated,
        ]

        if self.action in [
            "print_memo", "invoice_items",
            "list",
            "retrieve",
            "history",
        ]:
            permission_classes.append(
                HasShipmentMemoViewPermission
            )

        elif self.action == "read_invoice_file":
            permission_classes.append(HasShipmentMemoCreatePermission)

        elif self.action == "create":
            permission_classes.append(
                HasShipmentMemoCreatePermission
            )

        elif self.action in [
            "update",
            "partial_update",
        ]:
            permission_classes.append(
                HasShipmentMemoUpdatePermission
            )

        elif self.action == "destroy":
            permission_classes.append(
                HasShipmentMemoDeletePermission
            )

        elif self.action == "send_memo":
            permission_classes.append(
                HasShipmentMemoSendPermission
            )

        elif self.action == "cancel_memo":
            permission_classes.append(
                HasShipmentMemoCancelPermission
            )

        elif self.action == "create_revision":
            permission_classes.extend([
                HasShipmentMemoViewPermission,
                HasShipmentMemoCreatePermission,
            ])

        if self.action == 'invoice_items' and self.request.method == 'PUT':
            permission_classes.append(HasShipmentMemoUpdatePermission)
        return [
            permission_class()
            for permission_class in permission_classes
        ]

    @action(detail=False, methods=['post'], url_path='ler-nota', parser_classes=[MultiPartParser])
    def read_invoice_file(self, request):
        upload = request.FILES.get('file')
        if upload is None or upload.size > 10 * 1024 * 1024:
            return Response({'detail':'Arquivo obrigatório, máximo 10 MB.'}, status=400)
        try:
            data = read_invoice(upload)
            return Response(data)
        except (ValueError, ET.ParseError) as exc:
            return Response({'detail':str(exc)}, status=400)
        except RuntimeError as exc:
            return Response({'detail':str(exc)}, status=503)

    @action(detail=True, methods=['get', 'put'], url_path='notas')
    def invoice_items(self, request, pk=None):
        memo = self.get_object()
        if request.method == 'GET':
            return Response(InvoiceSerializer(memo.invoices.all(), many=True).data)
        if memo.status not in ('RASCUNHO', 'FALHA_ENVIO'):
            return Response({'detail':'Somente rascunhos podem ter notas alteradas.'}, status=409)
        serializer = InvoiceBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            memo.invoices.all().delete()
            for item in serializer.validated_data['invoices']:
                ShipmentMemoInvoice.objects.create(memo=memo, **item)
        return Response(InvoiceSerializer(memo.invoices.all(), many=True).data)

    @action(detail=True, methods=['get'], url_path='imprimir')
    def print_memo(self, request, pk=None):
        memo = self.get_object()
        content = generate_shipment_memo_pdf(shipment_memo=memo)
        response = HttpResponse(content, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{memo.code or "memorando"}.pdf"'
        return response

    def perform_destroy(self, instance):
        delete_shipment_memo(
            shipment_memo=instance,
        )

    def _serialize_detail(
        self,
        shipment_memo: ShipmentMemo,
    ) -> dict:
        instance = (
            self.get_queryset()
            .get(pk=shipment_memo.pk)
        )

        serializer = ShipmentMemoSerializer(
            instance,
            context=self.get_serializer_context(),
        )

        return serializer.data

    @extend_schema(
        tags=["memorando-remessas/memorandos"],
        summary="Enviar memorando de remessa",
        description=(
            "Valida o memorando, altera o status para "
            "PROCESSANDO_ENVIO e envia um e-mail com o PDF "
            "do memorando e os arquivos anexados. Em caso de "
            "sucesso, altera o status para ENVIADO. Em caso de "
            "erro, altera para FALHA_ENVIO."
        ),
        request=ShipmentMemoSendSerializer,
        responses={
            200: ShipmentMemoSerializer,
        },
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="enviar",
        url_name="enviar",
    )
    def send_memo(
        self,
        request,
        pk=None,
    ):
        shipment_memo = self.get_object()

        input_serializer = ShipmentMemoSendSerializer(
            data=request.data,
            context=self.get_serializer_context(),
        )

        input_serializer.is_valid(
            raise_exception=True,
        )

        shipment_memo = send_shipment_memo(
            shipment_memo=shipment_memo,
            user=request.user,
        )

        return Response(
            self._serialize_detail(
                shipment_memo
            ),
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["memorando-remessas/memorandos"],
        summary="Cancelar memorando de remessa",
        description=(
            "Cancela um memorando que jÃ¡ foi enviado. "
            "O motivo do cancelamento Ã© obrigatÃ³rio."
        ),
        request=ShipmentMemoCancelSerializer,
        responses={
            200: ShipmentMemoSerializer,
        },
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="cancelar",
        url_name="cancelar",
    )
    def cancel_memo(
        self,
        request,
        pk=None,
    ):
        shipment_memo = self.get_object()

        input_serializer = ShipmentMemoCancelSerializer(
            data=request.data,
            context=self.get_serializer_context(),
        )

        input_serializer.is_valid(
            raise_exception=True,
        )

        shipment_memo = cancel_shipment_memo(
            shipment_memo=shipment_memo,
            user=request.user,
            reason=(
                input_serializer
                .validated_data["reason"]
            ),
        )

        return Response(
            self._serialize_detail(
                shipment_memo
            ),
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["memorando-remessas/memorandos"],
        summary="Criar nova revisÃ£o",
        description=(
            "Cria uma nova revisÃ£o em RASCUNHO a partir "
            "da revisÃ£o mais recente de um memorando enviado "
            "ou cancelado."
        ),
        request=ShipmentMemoRevisionSerializer,
        responses={
            201: ShipmentMemoSerializer,
        },
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="nova-revisao",
        url_name="nova-revisao",
    )
    def create_revision(
        self,
        request,
        pk=None,
    ):
        shipment_memo = self.get_object()

        input_serializer = ShipmentMemoRevisionSerializer(
            data=request.data,
            context=self.get_serializer_context(),
        )

        input_serializer.is_valid(
            raise_exception=True,
        )

        new_revision = create_shipment_memo_revision(
            shipment_memo=shipment_memo,
            user=request.user,
        )

        return Response(
            self._serialize_detail(
                new_revision
            ),
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        tags=["memorando-remessas/memorandos"],
        summary="Listar histÃ³rico do memorando",
        description=(
            "Retorna as aÃ§Ãµes realizadas no memorando, "
            "incluindo criaÃ§Ã£o, alteraÃ§Ã£o, envio, cancelamento, "
            "revisÃµes e movimentaÃ§Ãµes de arquivos."
        ),
        responses={
            200: ShipmentMemoHistorySerializer(
                many=True,
            ),
        },
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="historico",
        url_name="historico",
    )
    def history(
        self,
        request,
        pk=None,
    ):
        shipment_memo = self.get_object()

        history_entries = (
            shipment_memo.history_entries
            .select_related(
                "actor",
            )
            .order_by(
                "-created_at",
                "-id",
            )
        )

        serializer = ShipmentMemoHistorySerializer(
            history_entries,
            many=True,
            context=self.get_serializer_context(),
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
