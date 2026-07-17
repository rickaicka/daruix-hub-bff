from django.urls import reverse
from rest_framework import serializers

from memorando_remessas.models import (
    ShipmentMemoFile,
)


class ShipmentMemoFileUploadSerializer(
    serializers.Serializer
):
    file = serializers.FileField(
        required=True,
        allow_empty_file=False,
    )


class ShipmentMemoFileSerializer(
    serializers.ModelSerializer
):
    uploaded_by_name = serializers.CharField(
        source="uploaded_by.name",
        read_only=True,
    )

    uploaded_by_username = serializers.CharField(
        source="uploaded_by.username",
        read_only=True,
    )

    download_url = serializers.SerializerMethodField()

    class Meta:
        model = ShipmentMemoFile

        fields = [
            "id",
            "shipment_memo",
            "original_name",
            "content_type",
            "size",
            "uploaded_by",
            "uploaded_by_name",
            "uploaded_by_username",
            "download_url",
            "created_at",
        ]

        read_only_fields = fields

    def get_download_url(self, obj):
        request = self.context.get("request")

        relative_url = reverse(
            (
                "memorando_remessas:"
                "shipment-memo-download-file"
            ),
            kwargs={
                "pk": obj.shipment_memo_id,
                "file_id": obj.id,
            },
        )

        if not request:
            return relative_url

        return request.build_absolute_uri(
            relative_url
        )