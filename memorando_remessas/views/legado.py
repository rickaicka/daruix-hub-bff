from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from memorando_remessas.serializers import (
    LegacyBridgeErrorSerializer,
    LegacyClientListResponseSerializer,
    LegacyClientQuerySerializer,
    LegacyWorkListResponseSerializer,
    LegacyWorkQuerySerializer,
    LegacyWorkSerializer,
)
from memorando_remessas.services.legacy_service import (
    LegacyBridgeError,
    get_legacy_work,
    list_legacy_clients,
    list_legacy_works,
)


def build_legacy_error_response(
    detail: str,
    code: str,
    response_status: int,
) -> Response:
    return Response(
        {
            "detail": detail,
            "code": code,
        },
        status=response_status,
    )


class LegacyClientListView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    @extend_schema(
        tags=["memorando-remessas/legado"],
        summary="Listar clientes do Access",
        description=(
            "Lista clientes comerciais que possuem obras ativas "
            "na tabela Cadastro Obra do Access."
        ),
        parameters=[
            OpenApiParameter(
                name="search",
                description=(
                    "Busca pelo nome ou documento do cliente."
                ),
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name="limit",
                description="Quantidade máxima de resultados.",
                required=False,
                type=int,
            ),
        ],
        responses={
            200: LegacyClientListResponseSerializer,
            400: OpenApiResponse(
                description="Parâmetros inválidos.",
            ),
            503: LegacyBridgeErrorSerializer,
        },
    )
    def get(self, request):
        query_serializer = LegacyClientQuerySerializer(
            data=request.query_params,
        )

        query_serializer.is_valid(
            raise_exception=True,
        )

        data = query_serializer.validated_data

        try:
            clients = list_legacy_clients(
                search=data["search"],
                limit=data["limit"],
            )

        except LegacyBridgeError as error:
            return build_legacy_error_response(
                detail=str(error),
                code="legacy_bridge_unavailable",
                response_status=(
                    status.HTTP_503_SERVICE_UNAVAILABLE
                ),
            )

        response_serializer = (
            LegacyClientListResponseSerializer(
                {
                    "count": len(clients),
                    "results": clients,
                }
            )
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_200_OK,
        )


class LegacyWorkListView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    @extend_schema(
        tags=["memorando-remessas/legado"],
        summary="Listar obras ativas do Access",
        description=(
            "Lista obras ativas da tabela Cadastro Obra. "
            "Pode filtrar pelo cliente e pesquisar por obra, "
            "centro de custo ou cliente."
        ),
        parameters=[
            OpenApiParameter(
                name="client_name",
                description="Nome exato do cliente.",
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name="client_document",
                description="Documento exato do cliente.",
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name="search",
                description=(
                    "Busca por nome da obra, centro de custo "
                    "ou nome do cliente."
                ),
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name="limit",
                description="Quantidade máxima de resultados.",
                required=False,
                type=int,
            ),
        ],
        responses={
            200: LegacyWorkListResponseSerializer,
            400: OpenApiResponse(
                description="Parâmetros inválidos.",
            ),
            503: LegacyBridgeErrorSerializer,
        },
    )
    def get(self, request):
        query_serializer = LegacyWorkQuerySerializer(
            data=request.query_params,
        )

        query_serializer.is_valid(
            raise_exception=True,
        )

        data = query_serializer.validated_data

        try:
            works = list_legacy_works(
                client_name=data["client_name"],
                client_document=data["client_document"],
                search=data["search"],
                limit=data["limit"],
            )

        except LegacyBridgeError as error:
            return build_legacy_error_response(
                detail=str(error),
                code="legacy_bridge_unavailable",
                response_status=(
                    status.HTTP_503_SERVICE_UNAVAILABLE
                ),
            )

        response_serializer = (
            LegacyWorkListResponseSerializer(
                {
                    "count": len(works),
                    "results": works,
                }
            )
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_200_OK,
        )


class LegacyWorkDetailView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    @extend_schema(
        tags=["memorando-remessas/legado"],
        summary="Detalhar obra ativa do Access",
        description=(
            "Retorna os dados de uma obra ativa pelo código "
            "legado da tabela Cadastro Obra."
        ),
        responses={
            200: LegacyWorkSerializer,
            404: OpenApiResponse(
                description=(
                    "Obra não encontrada ou finalizada."
                ),
            ),
            503: LegacyBridgeErrorSerializer,
        },
    )
    def get(
        self,
        request,
        legacy_work_id: int,
    ):
        try:
            work = get_legacy_work(
                legacy_work_id=legacy_work_id,
            )

        except LegacyBridgeError as error:
            return build_legacy_error_response(
                detail=str(error),
                code="legacy_bridge_unavailable",
                response_status=(
                    status.HTTP_503_SERVICE_UNAVAILABLE
                ),
            )

        if not work:
            return build_legacy_error_response(
                detail=(
                    "Obra não encontrada ou não está ativa "
                    "no sistema legado."
                ),
                code="legacy_work_not_found",
                response_status=status.HTTP_404_NOT_FOUND,
            )

        serializer = LegacyWorkSerializer(
            work,
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )