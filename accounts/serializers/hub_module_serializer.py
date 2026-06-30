from rest_framework import serializers

from accounts.models import HubModule


class HubModuleSerializer(serializers.ModelSerializer):
    nome = serializers.CharField(source="name", read_only=True)
    rota = serializers.CharField(source="route", read_only=True)
    icone = serializers.CharField(source="icon", read_only=True)
    permissao = serializers.CharField(source="permission.code", read_only=True)
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
            "legacy_enabled",
            "remote",
        ]

    def get_remote(self, obj):
        if not obj.mfe_enabled:
            return None

        return {
            "remote_name": obj.remote_name,
            "remote_entry": obj.remote_entry,
            "exposed_module": obj.exposed_module,
        }