from rest_framework import serializers


class LegacyClientQuerySerializer(serializers.Serializer):
    search = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=255,
        trim_whitespace=True,
    )

    limit = serializers.IntegerField(
        required=False,
        default=100,
        min_value=1,
        max_value=500,
    )


class LegacyWorkQuerySerializer(serializers.Serializer):
    client_name = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=255,
        trim_whitespace=True,
    )

    client_document = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=50,
        trim_whitespace=True,
    )

    search = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=255,
        trim_whitespace=True,
    )

    limit = serializers.IntegerField(
        required=False,
        default=100,
        min_value=1,
        max_value=500,
    )


class LegacyClientSerializer(serializers.Serializer):
    name = serializers.CharField(
        allow_blank=True,
    )

    document = serializers.CharField(
        allow_blank=True,
    )


class LegacyWorkSerializer(serializers.Serializer):
    legacy_work_id = serializers.IntegerField()

    legacy_proposal_id = serializers.IntegerField(
        allow_null=True,
    )

    cost_center = serializers.CharField(
        allow_blank=True,
    )

    work_name = serializers.CharField(
        allow_blank=True,
    )

    client_name = serializers.CharField(
        allow_blank=True,
    )

    client_document = serializers.CharField(
        allow_blank=True,
    )

    attention_to_suggestion = serializers.CharField(
        allow_blank=True,
    )

    delivery_address = serializers.CharField(
        allow_blank=True,
    )

    delivery_phone = serializers.CharField(
        allow_blank=True,
    )


class LegacyClientListResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()

    results = LegacyClientSerializer(
        many=True,
    )


class LegacyWorkListResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()

    results = LegacyWorkSerializer(
        many=True,
    )


class LegacyBridgeErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()
    code = serializers.CharField()