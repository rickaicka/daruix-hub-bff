from rest_framework import serializers

from accounts.models import HubMenuItem, HubModule
from accounts.services.hub_module_service import (
    annotate_user_menu_item_favorite,
    filter_user_menu_items_by_permission,
)


def _get_context_user(context):
    user = context.get("user")

    if user:
        return user

    request = context.get("request")
    return request.user if request else None


def _get_visible_children(menu_item, user):
    queryset = (
        menu_item.children
        .filter(is_active=True)
        .select_related("module")
        .prefetch_related("permissions")
        .order_by("order", "name")
    )

    queryset = filter_user_menu_items_by_permission(queryset, user)
    return annotate_user_menu_item_favorite(queryset, user)


class HubMenuItemSerializer(serializers.ModelSerializer):
    nome = serializers.CharField(source="name", read_only=True)
    rota = serializers.CharField(source="route", read_only=True)
    icone = serializers.CharField(source="icon", read_only=True)
    cor_icone = serializers.CharField(source="module.icon_color", read_only=True)
    permissao = serializers.SerializerMethodField()
    modulo_slug = serializers.CharField(source="module.slug", read_only=True)
    modulo_nome = serializers.CharField(source="module.name", read_only=True)
    favoritavel = serializers.BooleanField(source="favoritable", read_only=True)
    favorito = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()

    class Meta:
        model = HubMenuItem
        fields = [
            "slug",
            "nome",
            "rota",
            "icone",
            "cor_icone",
            "permissao",
            "modulo_slug",
            "modulo_nome",
            "favoritavel",
            "favorito",
            "desktop_enabled",
            "mobile_enabled",
            "legacy_enabled",
            "children",
        ]

    def get_permissao(self, obj):
        return sorted(
            permission.code
            for permission in obj.permissions.all()
            if permission.is_active
        )

    def get_favorito(self, obj):
        annotated_value = getattr(obj, "favorito", None)

        if annotated_value is not None:
            return bool(annotated_value)

        user = _get_context_user(self.context)

        if not user or not user.is_authenticated:
            return False

        return obj.user_favorites.filter(user=user).exists()

    def get_children(self, obj):
        user = _get_context_user(self.context)
        children = _get_visible_children(obj, user)

        return HubMenuItemSerializer(
            children,
            many=True,
            context=self.context,
        ).data


class HubModuleSerializer(serializers.ModelSerializer):
    nome = serializers.CharField(source="name", read_only=True)
    rota = serializers.CharField(source="route", read_only=True)
    icone = serializers.CharField(source="icon", read_only=True)
    cor_icone = serializers.CharField(source="icon_color", read_only=True)
    permissao = serializers.CharField(source="permission.code", read_only=True)
    children = serializers.SerializerMethodField()
    remote = serializers.SerializerMethodField()

    class Meta:
        model = HubModule
        fields = [
            "slug",
            "nome",
            "rota",
            "icone",
            "cor_icone",
            "permissao",
            "desktop_enabled",
            "mobile_enabled",
            "mfe_enabled",
            "legacy_enabled",
            "children",
            "remote",
        ]

    def get_children(self, obj):
        user = _get_context_user(self.context)
        queryset = (
            obj.menu_items
            .filter(parent__isnull=True, is_active=True)
            .select_related("module")
            .prefetch_related("permissions")
            .order_by("order", "name")
        )

        queryset = filter_user_menu_items_by_permission(queryset, user)
        queryset = annotate_user_menu_item_favorite(queryset, user)

        return HubMenuItemSerializer(
            queryset,
            many=True,
            context=self.context,
        ).data

    def get_remote(self, obj):
        if not obj.mfe_enabled:
            return None

        return {
            "remote_name": obj.remote_name,
            "remote_entry": obj.remote_entry,
            "exposed_module": obj.exposed_module,
        }


class HubMenuItemFavoriteSerializer(serializers.Serializer):
    favorito = serializers.BooleanField(required=True)


# Compatibilidade temporária com imports antigos.
HubModuleFavoriteSerializer = HubMenuItemFavoriteSerializer


