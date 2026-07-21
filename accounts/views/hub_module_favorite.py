from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.serializers.hub_module_serializer import (
    HubMenuItemFavoriteSerializer,
    HubMenuItemSerializer,
)
from accounts.services.hub_module_service import set_user_menu_item_favorite


class HubMenuItemFavoriteView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["hub/funcionalidades"],
        summary="Favoritar ou desfavoritar funcionalidade",
        request=HubMenuItemFavoriteSerializer,
        responses={
            200: HubMenuItemSerializer,
            400: OpenApiResponse(description="Payload inválido."),
            404: OpenApiResponse(
                description=(
                    "Funcionalidade não encontrada, não favoritada ou sem acesso."
                ),
            ),
        },
    )
    def patch(self, request, slug):
        serializer = HubMenuItemFavoriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        menu_item = set_user_menu_item_favorite(
            user=request.user,
            slug=slug,
            favorito=serializer.validated_data["favorito"],
        )

        if not menu_item:
            return Response(
                {
                    "detail": (
                        "Funcionalidade não encontrada, não favoritada "
                        "ou sem acesso para este usuário."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            HubMenuItemSerializer(
                menu_item,
                context={"user": request.user},
            ).data,
            status=status.HTTP_200_OK,
        )


# Mantém imports antigos funcionando até accounts/urls.py ser atualizado.
HubModuleFavoriteView = HubMenuItemFavoriteView
