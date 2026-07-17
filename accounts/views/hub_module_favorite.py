from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.serializers.hub_module_serializer import (
    HubModuleFavoriteSerializer,
    HubModuleSerializer,
)
from accounts.services.hub_module_service import set_user_module_favorite


class HubModuleFavoriteView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["hub/modulos"],
        summary="Favoritar ou desfavoritar módulo",
        request=HubModuleFavoriteSerializer,
        responses={
            200: HubModuleSerializer,
            400: OpenApiResponse(
                description="Payload inválido.",
            ),
            404: OpenApiResponse(
                description=(
                    "Módulo não encontrado ou sem acesso."
                ),
            ),
        },
    )
    def patch(self, request, slug):
        serializer = HubModuleFavoriteSerializer(
            data=request.data,
        )
        serializer.is_valid(
            raise_exception=True,
        )

        favorito = serializer.validated_data["favorito"]

        module = set_user_module_favorite(
            user=request.user,
            slug=slug,
            favorito=favorito,
        )

        if not module:
            return Response(
                {
                    "detail": (
                        "Módulo não encontrado ou sem acesso "
                        "para este usuário."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            HubModuleSerializer(
                module,
                context={
                    "user": request.user,
                },
            ).data,
            status=status.HTTP_200_OK,
        )