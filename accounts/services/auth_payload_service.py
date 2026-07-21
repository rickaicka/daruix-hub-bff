from accounts.models import User
from accounts.serializers.hub_module_serializer import HubModuleSerializer
from accounts.services.hub_module_service import get_user_modules
from accounts.services.permission_service import get_user_permission_codes


def build_authenticated_user_payload(user: User) -> dict:
    modules = get_user_modules(user)

    serialized_modules = HubModuleSerializer(
        modules,
        many=True,
        context={"user": user},
    ).data

    return {
        "id_usuario": user.id,
        "username": user.username,
        "nome": user.name,
        "email": user.email,
        "tipo_usuario": user.user_type,
        "grupo": user.group.name if user.group else None,
        "permissoes": get_user_permission_codes(user),
        "modulos": serialized_modules,
        "origem": user.user_origin,
        "ativo": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }


def build_login_user_payload(user: User) -> dict:
    return build_authenticated_user_payload(user)

