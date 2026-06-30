from accounts.models import (
    HubModule,
    PermissionCode,
    UserAppAccess,
    UserPermissionOverride,
)
from accounts._old.services.hub_permission_policy import (
    get_permission_action,
    get_permission_module_slug,
    is_allowed_permission_code,
)


def get_user_permission_codes(user):
    """
    Retorna permissões finais do usuário.

    Regra:
    permissões herdadas dos grupos
    + overrides allow
    - overrides deny

    Depois filtra apenas permissões permitidas pela política moderna
    do Daruix Hub.

    Isso evita retornar permissões antigas/granulares vindas do Access,
    como:
    - employee.acompemail.approve
    - employee.cadobra.delete
    - employee.tcpo.export
    """

    group_permissions = PermissionCode.objects.filter(
        group_permissions__group__memberships__user=user
    ).values_list("code", flat=True)

    allowed_overrides = PermissionCode.objects.filter(
        user_overrides__user=user,
        user_overrides__effect=UserPermissionOverride.ALLOW,
    ).values_list("code", flat=True)

    denied_overrides = PermissionCode.objects.filter(
        user_overrides__user=user,
        user_overrides__effect=UserPermissionOverride.DENY,
    ).values_list("code", flat=True)

    permissions = set(group_permissions)
    permissions.update(allowed_overrides)
    permissions.difference_update(denied_overrides)

    allowed_permissions = {
        permission
        for permission in permissions
        if is_allowed_permission_code(permission)
    }

    return sorted(allowed_permissions)


def user_has_permission(user, permission_code):
    """
    Verifica se o usuário possui uma permissão moderna permitida.

    Se a permissão nem fizer parte da política oficial do Hub,
    retorna False diretamente.
    """

    if not is_allowed_permission_code(permission_code):
        return False

    return permission_code in get_user_permission_codes(user)


def sync_user_app_access(user):
    """
    Atualiza os módulos visíveis para o usuário com base nas permissões.

    Apenas módulos com permissão moderna de 'view' aparecem como acesso
    ativo para o usuário.

    Exemplo:
    employee.purchase_orders.view
    libera o módulo purchase_orders.

    Permissões antigas do Access são ignoradas.
    """

    if not user.user_type:
        return []

    permission_codes = get_user_permission_codes(user)

    module_slugs = set()

    for code in permission_codes:
        module_slug = get_permission_module_slug(code)
        action = get_permission_action(code)

        if not module_slug or not action:
            continue

        if action == "view":
            module_slugs.add(module_slug)

    modules = HubModule.objects.filter(
        user_type=user.user_type,
        slug__in=module_slugs,
        is_active=True,
    )

    for module in modules:
        UserAppAccess.objects.update_or_create(
            user=user,
            module=module,
            defaults={"is_active": True},
        )

    UserAppAccess.objects.filter(user=user).exclude(
        module__in=modules
    ).update(is_active=False)

    return list(modules)


def get_user_modules(user):
    """
    Retorna os módulos visíveis/ativos do usuário.

    Antes de retornar, sincroniza UserAppAccess com base nas permissões
    modernas permitidas.
    """

    sync_user_app_access(user)

    return HubModule.objects.filter(
        user_access__user=user,
        user_access__is_active=True,
        is_active=True,
    ).order_by("order", "name")