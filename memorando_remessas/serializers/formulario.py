from rest_framework import serializers

from memorando_remessas.models import ShipmentMemoOption


class ShipmentMemoOptionSerializer(
    serializers.ModelSerializer
):
    type_label = serializers.CharField(
        source="get_option_type_display",
        read_only=True,
    )

    class Meta:
        model = ShipmentMemoOption

        fields = [
            "id",
            "option_type",
            "type_label",
            "code",
            "name",
            "description",
            "order",
        ]


class ShipmentMemoOptionsResponseSerializer(
    serializers.Serializer
):
    species = ShipmentMemoOptionSerializer(
        many=True,
    )

    purposes = ShipmentMemoOptionSerializer(
        many=True,
    )

    requests = ShipmentMemoOptionSerializer(
        many=True,
    )


class ResponsibleUserQuerySerializer(
    serializers.Serializer
):
    search = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=150,
        trim_whitespace=True,
    )

    limit = serializers.IntegerField(
        required=False,
        default=50,
        min_value=1,
        max_value=200,
    )


class ResponsibleUserSerializer(
    serializers.Serializer
):
    id = serializers.IntegerField()

    username = serializers.CharField()

    name = serializers.CharField()

    email = serializers.EmailField(
        allow_blank=True,
    )

    group_name = serializers.CharField(
        source="group.name",
        allow_null=True,
        read_only=True,
    )

    selected_by_default = serializers.SerializerMethodField()

    def get_selected_by_default(self, obj):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return False

        return obj.pk == request.user.pk


class ResponsibleUserListResponseSerializer(
    serializers.Serializer
):
    count = serializers.IntegerField()

    results = ResponsibleUserSerializer(
        many=True,
    )