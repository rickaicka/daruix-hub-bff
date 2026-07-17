from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from rest_framework import serializers
from accounts.serializers.hub_module_serializer import HubModuleSerializer
from accounts.services.hub_module_service import get_user_modules
from accounts.services.permission_service import get_user_permission_codes


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            name="Login request",
            value={
                "username": "ricardo",
                "password": "123456",
            },
            request_only=True,
        ),
    ]
)
class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(
        required=True,
        allow_blank=False,
        help_text="Username used to authenticate the user.",
    )

    password = serializers.CharField(
        required=True,
        write_only=True,
        trim_whitespace=False,
        help_text="User password.",
    )


class HubModuleRemoteSerializer(serializers.Serializer):
    remote_name = serializers.CharField(
        allow_blank=True,
        allow_null=True,
    )

    remote_entry = serializers.CharField(
        allow_blank=True,
        allow_null=True,
    )

    exposed_module = serializers.CharField(
        allow_blank=True,
        allow_null=True,
    )

class AuthenticatedUserSerializer(serializers.Serializer):
    id_usuario = serializers.IntegerField()
    username = serializers.CharField()
    nome = serializers.CharField()

    email = serializers.EmailField(
        allow_blank=True,
        allow_null=True,
    )

    tipo_usuario = serializers.CharField(
        allow_null=True,
        required=False,
    )

    grupo = serializers.CharField(
        allow_null=True,
        required=False,
    )

    permissoes = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )

    modulos = HubModuleSerializer(
        many=True,
        required=False,
    )

    origem = serializers.CharField(
        allow_null=True,
        required=False,
    )

    ativo = serializers.BooleanField(
        required=False,
    )

    is_staff = serializers.BooleanField(
        required=False,
    )

    is_superuser = serializers.BooleanField(
        required=False,
    )

class SessionSerializer(serializers.Serializer):
    id = serializers.CharField()
    expira_em = serializers.DateTimeField()
    inatividade_minutos = serializers.IntegerField()


class RefreshSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(
        required=True,
        help_text="Refresh token returned by login.",
    )


class RefreshResponseSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    token_type = serializers.CharField()
    sessao = SessionSerializer()

class LoginResponseSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    token_type = serializers.CharField()
    usuario = AuthenticatedUserSerializer()
    sessao = SessionSerializer()


class MeResponseSerializer(serializers.Serializer):
    id_usuario = serializers.IntegerField(
        source="id",
        read_only=True,
    )

    username = serializers.CharField(
        read_only=True,
    )

    nome = serializers.SerializerMethodField()

    email = serializers.EmailField(
        allow_blank=True,
        allow_null=True,
        read_only=True,
    )

    tipo_usuario = serializers.CharField(
        source="user_type",
        allow_null=True,
        read_only=True,
    )

    grupo = serializers.SerializerMethodField()

    permissoes = serializers.SerializerMethodField()
    modulos = serializers.SerializerMethodField()

    origem = serializers.CharField(
        source="user_origin",
        allow_null=True,
        read_only=True,
    )

    ativo = serializers.BooleanField(
        source="is_active",
        read_only=True,
    )

    is_staff = serializers.BooleanField(
        read_only=True,
    )

    is_superuser = serializers.BooleanField(
        read_only=True,
    )

    def get_nome(self, user):
        if getattr(user, "name", None):
            return user.name

        full_name = user.get_full_name()

        if full_name:
            return full_name

        return user.username

    def get_grupo(self, user):
        if not user.group:
            return None

        return user.group.name

    def get_permissoes(self, user):
        return get_user_permission_codes(user)

    def get_modulos(self, user):
        modules = get_user_modules(user)

        return HubModuleSerializer(
            modules,
            many=True,
            context={"user": user},
        ).data


class LogoutSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(
        required=True,
        help_text="Refresh token returned by login.",
    )


class LogoutResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()