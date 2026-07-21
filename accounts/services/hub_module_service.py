from django.db.models import BooleanField, Exists, OuterRef, Q, Value

from accounts.models import (
    HubMenuItem,
    HubModule,
    UserHubMenuItemFavorite,
)
from accounts.services.permission_service import get_user_permission_codes


def annotate_user_menu_item_favorite(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.annotate(
            favorito=Value(False, output_field=BooleanField())
        )

    favorite_query = UserHubMenuItemFavorite.objects.filter(
        user=user,
        menu_item_id=OuterRef("pk"),
    )

    return queryset.annotate(favorito=Exists(favorite_query))


def filter_user_menu_items_by_permission(queryset, user):
    """
    Filtra funcionalidades conforme as permissões do usuário.

    Regras:
    - superusuário acessa todas as funcionalidades ativas;
    - sem permissões configuradas, a funcionalidade herda o acesso do módulo;
    - com permissões configuradas, basta o usuário possuir uma delas.
    """

    if not user or not user.is_authenticated:
        return queryset.none()

    if user.is_superuser:
        return queryset

    permission_codes = get_user_permission_codes(user)

    return queryset.filter(
        Q(permissions__isnull=True)
        | Q(
            permissions__is_active=True,
            permissions__code__in=permission_codes,
        )
    ).distinct()


def get_user_modules(user):
    """Retorna os módulos ativos que o usuário pode acessar."""

    if not user or not user.is_authenticated:
        return HubModule.objects.none()

    queryset = (
        HubModule.objects
        .filter(is_active=True)
        .select_related("permission")
        .order_by("order", "name")
    )

    if user.is_superuser:
        return queryset

    permission_codes = get_user_permission_codes(user)

    if not permission_codes:
        return HubModule.objects.none()

    return queryset.filter(
        permission__is_active=True,
        permission__code__in=permission_codes,
    )


def get_user_menu_items(user):
    """Retorna todas as funcionalidades que o usuário pode acessar."""

    if not user or not user.is_authenticated:
        return HubMenuItem.objects.none()

    accessible_module_ids = get_user_modules(user).values("pk")

    queryset = (
        HubMenuItem.objects
        .filter(
            module_id__in=accessible_module_ids,
            module__is_active=True,
            is_active=True,
        )
        .select_related("module", "parent")
        .prefetch_related("permissions")
        .order_by("module__order", "module__name", "order", "name")
    )

    queryset = filter_user_menu_items_by_permission(queryset, user)

    return annotate_user_menu_item_favorite(queryset, user)


def get_user_menu_item_by_slug(user, slug):
    if not slug:
        return None

    return get_user_menu_items(user).filter(slug=slug).first()


def set_user_menu_item_favorite(user, slug, favorito: bool):
    menu_item = get_user_menu_item_by_slug(user, slug)

    if not menu_item or not menu_item.favoritable or not menu_item.route:
        return None

    if favorito:
        UserHubMenuItemFavorite.objects.get_or_create(
            user=user,
            menu_item_id=menu_item.id,
        )
    else:
        UserHubMenuItemFavorite.objects.filter(
            user=user,
            menu_item_id=menu_item.id,
        ).delete()

    menu_item.favorito = favorito
    return menu_item


