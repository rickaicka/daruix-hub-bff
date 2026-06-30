from accounts.models import HubModule
from accounts.services.permission_service import get_user_permission_codes


def get_user_modules(user):
    """
    Retorna os módulos do Hub que o usuário pode acessar.

    Regra:
    - superuser vê todos os módulos ativos;
    - usuário comum vê módulos cuja permissão mínima está na lista de permissões.
    """

    if not user or not user.is_authenticated:
        return HubModule.objects.none()

    if user.is_superuser:
        return (
            HubModule.objects
            .filter(is_active=True)
            .select_related("permission")
            .order_by("order", "name")
        )

    permission_codes = get_user_permission_codes(user)

    if not permission_codes:
        return HubModule.objects.none()

    return (
        HubModule.objects
        .filter(
            is_active=True,
            permission__is_active=True,
            permission__code__in=permission_codes,
        )
        .select_related("permission")
        .order_by("order", "name")
    )