from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Prefetch
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .choices import DataOrigin
from .models import ServiceComposition, ServiceCompositionItem, ServiceCompositionVersion, Supply
from .serializers import (
    CompositionVersionSerializer,
    ServiceCompositionReadSerializer,
    ServiceCompositionWriteSerializer,
    SupplySerializer,
)
from .services.compositions import new_version, publish


class SupplyViewSet(viewsets.ModelViewSet):
    serializer_class = SupplySerializer
    queryset = Supply.objects.all()
    search_fields = ("description", "code")
    ordering_fields = ("description", "code", "updated_at")
    filterset_fields = ("origin", "supply_type", "is_active", "unit")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.origin == DataOrigin.LEGACY:
            raise ValidationError("Insumos legados são imutáveis.")
        instance.is_active = False
        instance.save(update_fields=("is_active", "updated_at"))
        return Response(status=status.HTTP_204_NO_CONTENT)


class ServiceCompositionViewSet(viewsets.ModelViewSet):
    queryset = ServiceComposition.objects.prefetch_related(
        Prefetch(
            "versions",
            queryset=ServiceCompositionVersion.objects.prefetch_related(
                Prefetch("items", queryset=ServiceCompositionItem.objects.select_related("supply", "subcomposition"))
            ),
        )
    )
    search_fields = ("name", "code")
    ordering_fields = ("name", "code", "updated_at")
    filterset_fields = ("origin", "is_active")

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return ServiceCompositionWriteSerializer
        return ServiceCompositionReadSerializer

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.origin == DataOrigin.LEGACY:
            raise ValidationError("Composições legadas são imutáveis.")
        instance.is_active = False
        instance.save(update_fields=("is_active", "updated_at"))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("post",))
    def publish(self, request, pk=None):
        try:
            version = publish(self.get_object())
        except DjangoValidationError as error:
            raise ValidationError(error.messages) from error
        return Response(CompositionVersionSerializer(version).data)

    @action(detail=True, methods=("post",), url_path="new-version")
    def new_version(self, request, pk=None):
        try:
            version = new_version(self.get_object())
        except DjangoValidationError as error:
            raise ValidationError(error.messages) from error
        return Response(CompositionVersionSerializer(version).data, status=status.HTTP_201_CREATED)
