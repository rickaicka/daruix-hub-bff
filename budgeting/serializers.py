from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .choices import DataOrigin
from .models import ServiceComposition, ServiceCompositionItem, ServiceCompositionVersion, Supply
from .services.compositions import create_composition, update_draft


class SupplySerializer(serializers.ModelSerializer):
    class Meta:
        model = Supply
        fields = (
            "id",
            "origin",
            "legacy_id",
            "code",
            "description",
            "supply_type",
            "unit",
            "specification",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("origin", "legacy_id", "created_at", "updated_at")

    def create(self, validated_data):
        return Supply.objects.create(origin=DataOrigin.HUB, **validated_data)

    def validate(self, attrs):
        if self.instance and self.instance.origin == DataOrigin.LEGACY:
            raise serializers.ValidationError("Insumos legados são imutáveis.")
        return attrs


class CompositionItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=24, decimal_places=4, read_only=True)

    class Meta:
        model = ServiceCompositionItem
        fields = (
            "id",
            "item_type",
            "supply",
            "subcomposition",
            "description_snapshot",
            "unit_snapshot",
            "coefficient",
            "material_unit_price",
            "labor_unit_price",
            "equipment_unit_price",
            "position",
            "subtotal",
        )
        read_only_fields = ("id", "subtotal")


class CompositionVersionSerializer(serializers.ModelSerializer):
    items = CompositionItemSerializer(many=True, read_only=True)

    class Meta:
        model = ServiceCompositionVersion
        fields = (
            "id",
            "number",
            "status",
            "origin",
            "unit",
            "material_total",
            "labor_total",
            "equipment_total",
            "total",
            "imported_at",
            "published_at",
            "items",
        )


class ServiceCompositionReadSerializer(serializers.ModelSerializer):
    latest_version = serializers.SerializerMethodField()

    class Meta:
        model = ServiceComposition
        fields = (
            "id",
            "origin",
            "legacy_id",
            "code",
            "name",
            "is_active",
            "latest_version",
            "created_at",
            "updated_at",
        )

    def get_latest_version(self, obj):
        version = obj.latest_version
        return CompositionVersionSerializer(version).data if version else None


class ServiceCompositionWriteSerializer(serializers.ModelSerializer):
    unit = serializers.CharField(max_length=30, allow_blank=True, write_only=True)
    items = CompositionItemSerializer(many=True, write_only=True)

    class Meta:
        model = ServiceComposition
        fields = ("id", "code", "name", "is_active", "unit", "items")
        read_only_fields = ("id",)

    def create(self, validated_data):
        try:
            return create_composition(validated_data)
        except DjangoValidationError as error:
            detail = getattr(error, "message_dict", error.messages)
            raise serializers.ValidationError(detail) from error

    def update(self, instance, validated_data):
        try:
            return update_draft(instance, validated_data)
        except DjangoValidationError as error:
            detail = getattr(error, "message_dict", error.messages)
            raise serializers.ValidationError(detail) from error

    def to_representation(self, instance):
        return ServiceCompositionReadSerializer(instance, context=self.context).data
