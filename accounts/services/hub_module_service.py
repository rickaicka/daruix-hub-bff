from django.db.models import BooleanField, Exists, OuterRef, Value

from accounts.models import HubModule, UserHubModuleFavorite
from accounts.services.permission_service import get_user_permission_codes


def annotate_user_favorite(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.annotate(
            favorito=Value(False, output_field=BooleanField())
        )

    favorite_query = UserHubModuleFavorite.objects.filter(
        user=user,
        module_id=OuterRef("pk"),
    )

    return queryset.annotate(
        favorito=Exists(favorite_query)
    )


def get_user_modules(user):
    """
    Retorna os módulos do Hub que o usuário pode acessar.

    Regra:
    - superuser vê todos os módulos ativos;
    - usuário comum vê módulos cuja permissão mínima está na lista de permissões;
    - cada módulo vem anotado com favorito=True/False para o usuário.
    """

    if not user or not user.is_authenticated:
        return HubModule.objects.none()

    base_queryset = (
        HubModule.objects
        .filter(is_active=True)
        .select_related("permission")
        .order_by("order", "name")
    )

    if user.is_superuser:
        return annotate_user_favorite(base_queryset, user)

    permission_codes = get_user_permission_codes(user)

    if not permission_codes:
        return HubModule.objects.none()

    queryset = base_queryset.filter(
        permission__is_active=True,
        permission__code__in=permission_codes,
    )

    return annotate_user_favorite(queryset, user)


def get_user_module_by_slug(user, slug):
    if not slug:
        return None

    return get_user_modules(user).filter(slug=slug).first()


def set_user_module_favorite(user, slug, favorito: bool):
    module = get_user_module_by_slug(user, slug)

    if not module:
        return None

    if favorito:
        UserHubModuleFavorite.objects.get_or_create(
            user=user,
            module_id=module.id,
        )
    else:
        UserHubModuleFavorite.objects.filter(
            user=user,
            module_id=module.id,
        ).delete()

    module.favorito = favorito

    return module