from rest_framework import serializers

from memorando_remessas.models import (
    ShipmentMemo,
    ShipmentMemoHistory,
    ShipmentMemoResponsible,
)
from memorando_remessas.serializers.arquivo import (
    ShipmentMemoFileSerializer,
)
from memorando_remessas.serializers.formulario import (
    ShipmentMemoOptionSerializer,
)
from memorando_remessas.services import (
    create_shipment_memo,
    update_shipment_memo,
)


class ShipmentMemoResponsibleSerializer(
    serializers.ModelSerializer
):
    user_id = serializers.IntegerField(
        source="user.id",
        read_only=True,
    )

    username = serializers.CharField(
        source="user.username",
        read_only=True,
    )

    name = serializers.CharField(
        source="user.name",
        read_only=True,
    )

    email = serializers.EmailField(
        source="user.email",
        read_only=True,
    )

    class Meta:
        model = ShipmentMemoResponsible

        fields = [
            "id",
            "user_id",
            "username",
            "name",
            "email",
            "is_primary",
            "created_at",
        ]

        read_only_fields = fields


class ShipmentMemoListSerializer(
    serializers.ModelSerializer
):
    status_label = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    primary_responsible_name = (
        serializers.SerializerMethodField()
    )

    class Meta:
        model = ShipmentMemo

        fields = [
            "id",
            "code",
            "revision",
            "status",
            "status_label",
            "legacy_work_id",
            "cost_center",
            "work_name",
            "client_name",
            "shipping_date",
            "subject",
            "primary_responsible_name",
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields

    def get_primary_responsible_name(
        self,
        obj,
    ):
        for responsible in obj.responsible_links.all():
            if responsible.is_primary:
                return (
                    responsible.user.name
                    or responsible.user.username
                )

        return None


class ShipmentMemoSerializer(
    serializers.ModelSerializer
):
    legacy_work_id = serializers.IntegerField(
        min_value=1,
        required=True,
    )

    recipient_emails = serializers.ListField(
        child=serializers.EmailField(),
        read_only=True,
    )

    cc_emails = serializers.ListField(
        child=serializers.EmailField(),
        read_only=True,
    )

    responsible_user_ids = serializers.ListField(
        child=serializers.IntegerField(
            min_value=1,
        ),
        required=False,
        write_only=True,
        allow_empty=True,
    )

    option_ids = serializers.ListField(
        child=serializers.IntegerField(
            min_value=1,
        ),
        required=False,
        write_only=True,
        allow_empty=True,
    )

    status_label = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    work_source_label = serializers.CharField(
        source="get_work_source_display",
        read_only=True,
    )

    responsible_users = (
        ShipmentMemoResponsibleSerializer(
            source="responsible_links",
            many=True,
            read_only=True,
        )
    )

    selected_options = ShipmentMemoOptionSerializer(
        source="options",
        many=True,
        read_only=True,
    )

    attachments = ShipmentMemoFileSerializer(
        source="files",
        many=True,
        read_only=True,
    )

    created_by_name = serializers.CharField(
        source="created_by.name",
        read_only=True,
    )

    updated_by_name = serializers.CharField(
        source="updated_by.name",
        read_only=True,
    )

    sent_by_name = serializers.CharField(
        source="sent_by.name",
        read_only=True,
        allow_null=True,
    )

    cancelled_by_name = serializers.CharField(
        source="cancelled_by.name",
        read_only=True,
        allow_null=True,
    )

    last_send_error = serializers.CharField(
        read_only=True,
    )

    class Meta:
        model = ShipmentMemo

        fields = [
            "id",
            "code",
            "sequence_number",
            "revision",
            "revised_from",
            "status",
            "status_label",
            "work_source",
            "work_source_label",
            "legacy_work_id",
            "legacy_proposal_id",
            "cost_center",
            "work_name",
            "client_name",
            "client_document",
            "shipping_date",
            "subject",
            "attention_to",
            "recipient_emails",
            "cc_emails",
            "notes",
            "responsible_user_ids",
            "responsible_users",
            "option_ids",
            "selected_options",
            "attachments",
            "created_by",
            "created_by_name",
            "updated_by",
            "updated_by_name",
            "sent_by",
            "sent_by_name",
            "sent_at",
            "last_send_error",
            "cancelled_by",
            "cancelled_by_name",
            "cancelled_at",
            "cancellation_reason",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "code",
            "sequence_number",
            "revision",
            "revised_from",
            "status",
            "work_source",
            "legacy_proposal_id",
            "cost_center",
            "work_name",
            "client_name",
            "client_document",
            "recipient_emails",
            "cc_emails",
            "created_by",
            "updated_by",
            "sent_by",
            "sent_at",
            "last_send_error",
            "cancelled_by",
            "cancelled_at",
            "cancellation_reason",
            "created_at",
            "updated_at",
        ]

    def create(
        self,
        validated_data,
    ):
        request = self.context["request"]

        return create_shipment_memo(
            validated_data=validated_data,
            user=request.user,
        )

    def update(
        self,
        instance,
        validated_data,
    ):
        request = self.context["request"]

        return update_shipment_memo(
            shipment_memo=instance,
            validated_data=validated_data,
            user=request.user,
        )


class ShipmentMemoSendSerializer(
    serializers.Serializer
):
    pass


class ShipmentMemoCancelSerializer(
    serializers.Serializer
):
    reason = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=2000,
        trim_whitespace=True,
    )


class ShipmentMemoRevisionSerializer(
    serializers.Serializer
):
    pass


class ShipmentMemoHistorySerializer(
    serializers.ModelSerializer
):
    action_label = serializers.CharField(
        source="get_action_display",
        read_only=True,
    )

    actor_name = serializers.CharField(
        source="actor.name",
        read_only=True,
    )

    actor_username = serializers.CharField(
        source="actor.username",
        read_only=True,
    )

    class Meta:
        model = ShipmentMemoHistory

        fields = [
            "id",
            "action",
            "action_label",
            "actor",
            "actor_name",
            "actor_username",
            "description",
            "before_data",
            "after_data",
            "metadata",
            "created_at",
        ]

        read_only_fields = fields