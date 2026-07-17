from rest_framework import serializers

from accounts.models import HubModule


class HubModuleSerializer(serializers.ModelSerializer):
    nome = serializers.CharField(source="name", read_only=True)
    rota = serializers.CharField(source="route", read_only=True)
    icone = serializers.CharField(source="icon", read_only=True)
    permissao = serializers.CharField(source="permission.code", read_only=True)
    favorito = serializers.SerializerMethodField()
    remote = serializers.SerializerMethodField()

    class Meta:
        model = HubModule
        fields = [
            "slug",
            "nome",
            "rota",
            "icone",
            "permissao",
            "desktop_enabled",
            "mobile_enabled",
            "mfe_enabled",
            "favorito",
            "legacy_enabled",
            "remote",
        ]

    def get_favorito(self, obj):
        annotated_value = getattr(obj, "favorito", None)

        if annotated_value is not None:
            return bool(annotated_value)

        user = self.context.get("user")

        request = self.context.get("request")
        if not user and request:
            user = request.user

        if not user or not user.is_authenticated:
            return False

        return obj.user_favorites.filter(user=user).exists()

    def get_remote(self, obj):
        if not obj.mfe_enabled:
            return None

        return {
            "remote_name": obj.remote_name,
            "remote_entry": obj.remote_entry,
            "exposed_module": obj.exposed_module,
        }


class HubModuleFavoriteSerializer(serializers.Serializer):
    favorito = serializers.BooleanField(required=True)