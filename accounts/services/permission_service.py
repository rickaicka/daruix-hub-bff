from accounts.models import User


def get_user_permission_codes(user: User) -> list[str]:
    if not user or not user.is_authenticated:
        return []

    if user.is_superuser:
        return ["*"]

    if not user.group:
        return []

    return list(
        user.group.group_permissions.filter(
            is_active=True,
            group__is_active=True,
            permission__is_active=True,
        )
        .values_list("permission__code", flat=True)
        .distinct()
        .order_by("permission__code")
    )


def user_has_permission(user: User, permission_code: str) -> bool:
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if not user.group:
        return False

    return user.group.group_permissions.filter(
        is_active=True,
        permission__is_active=True,
        permission__code=permission_code,
    ).exists()


def user_has_any_permission(user: User, permission_codes: list[str]) -> bool:
    if not permission_codes:
        return False

    return any(
        user_has_permission(user, permission_code)
        for permission_code in permission_codes
    )


def user_has_all_permissions(user: User, permission_codes: list[str]) -> bool:
    if not permission_codes:
        return False

    return all(
        user_has_permission(user, permission_code)
        for permission_code in permission_codes
    )