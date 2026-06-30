import re
import unicodedata


def get_row_value(row, field_name, default=None):
    try:
        return getattr(row, field_name)
    except AttributeError:
        return default


def normalize_text(value):
    if value is None:
        return ""

    return str(value).strip()


def normalize_slug(value):
    value = normalize_text(value).lower()

    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")

    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = value.strip("_")

    return value or "default"


def is_yes(value):
    value = normalize_text(value).lower()

    return value in [
        "sim",
        "s",
        "yes",
        "true",
        "1",
    ]


def infer_user_type(access_user):
    """
    Por enquanto, todo usuário vindo do Access é tratado como Colaborador.

    Futuramente, se encontrarmos tabelas separadas para cliente/fornecedor,
    essa função pode passar a inferir:
    - employee
    - client
    - supplier
    """

    return {
        "slug": "employee",
        "name": "Colaborador",
        "legacy_id": None,
        "legacy_name": normalize_text(
            get_row_value(access_user, "usuGrupo")
        ),
    }


def infer_groups(access_user):
    group_name = normalize_text(
        get_row_value(access_user, "usuGrupo")
    ) or "Operacional"

    return [
        {
            "slug": normalize_slug(group_name),
            "name": group_name,
            "legacy_id": None,
            "legacy_name": group_name,
        }
    ]


def module_dashboard():
    return {
        "slug": "dashboard",
        "name": "Painel",
        "description": "Painel principal do Hub.",
        "route": "/painel",
        "icon": "layout-dashboard",
        "desktop_enabled": True,
        "mobile_enabled": True,
        "legacy_enabled": False,
        "order": 1,
        "is_active": True,
        "legacy_object_name": "usuPainel",
    }


def module_deductibles():
    return {
        "slug": "deductibles",
        "name": "Dedutíveis",
        "description": "Módulo de dedutíveis.",
        "route": "/dedutiveis",
        "icon": "receipt",
        "desktop_enabled": True,
        "mobile_enabled": True,
        "legacy_enabled": False,
        "order": 2,
        "is_active": True,
        "legacy_object_name": "usuDedutiveis",
    }


def module_purchase_orders():
    return {
        "slug": "purchase_orders",
        "name": "Ordens de Compra",
        "description": "Gestão de ordens de compra.",
        "route": "/ordens-compra",
        "icon": "file-text",
        "desktop_enabled": True,
        "mobile_enabled": True,
        "legacy_enabled": False,
        "order": 3,
        "is_active": True,
        "legacy_object_name": "Ordem de Compra",
    }


def module_admin():
    return {
        "slug": "admin",
        "name": "Administração",
        "description": "Administração do Daruix Hub.",
        "route": "/admin",
        "icon": "settings",
        "desktop_enabled": True,
        "mobile_enabled": False,
        "legacy_enabled": False,
        "order": 99,
        "is_active": True,
        "legacy_object_name": "Admin",
    }


def build_permission(user_type_slug, module, action, action_name):
    code = f"{user_type_slug}.{module['slug']}.{action}"

    return {
        "code": code,
        "name": action_name,
        "description": f"{action_name} em {module['name']}",
        "legacy_permission_name": action_name,
        "module": module,
    }


def build_permissions(access_user, user_type):
    user_type_slug = user_type["slug"]

    group = normalize_slug(
        get_row_value(access_user, "usuGrupo")
    )

    approval_limit = get_row_value(access_user, "usuAlcada", 0) or 0

    try:
        approval_limit = int(approval_limit)
    except Exception:
        approval_limit = 0

    permissions = []
    modules = []

    dashboard = module_dashboard()
    deductibles = module_deductibles()
    purchase_orders = module_purchase_orders()
    admin = module_admin()

    if is_yes(get_row_value(access_user, "usuPainel")):
        modules.append(dashboard)

        permissions.append(
            build_permission(
                user_type_slug=user_type_slug,
                module=dashboard,
                action="view",
                action_name="Visualizar",
            )
        )

    if is_yes(get_row_value(access_user, "usuDedutiveis")):
        modules.append(deductibles)

        permissions.append(
            build_permission(
                user_type_slug=user_type_slug,
                module=deductibles,
                action="view",
                action_name="Visualizar",
            )
        )

    modules.append(purchase_orders)

    permissions.append(
        build_permission(
            user_type_slug=user_type_slug,
            module=purchase_orders,
            action="view",
            action_name="Visualizar",
        )
    )

    if group in ["diretoria", "administrador"]:
        permissions.extend(
            [
                build_permission(
                    user_type_slug=user_type_slug,
                    module=purchase_orders,
                    action="create",
                    action_name="Criar",
                ),
                build_permission(
                    user_type_slug=user_type_slug,
                    module=purchase_orders,
                    action="update",
                    action_name="Alterar",
                ),
                build_permission(
                    user_type_slug=user_type_slug,
                    module=purchase_orders,
                    action="delete",
                    action_name="Excluir",
                ),
                build_permission(
                    user_type_slug=user_type_slug,
                    module=purchase_orders,
                    action="export",
                    action_name="Exportar",
                ),
            ]
        )

    if approval_limit > 0:
        permissions.append(
            build_permission(
                user_type_slug=user_type_slug,
                module=purchase_orders,
                action="approve",
                action_name="Aprovar",
            )
        )

    if group in ["diretoria", "administrador"]:
        modules.append(admin)

        permissions.extend(
            [
                build_permission(
                    user_type_slug=user_type_slug,
                    module=admin,
                    action="view",
                    action_name="Visualizar",
                ),
                build_permission(
                    user_type_slug=user_type_slug,
                    module=admin,
                    action="manage",
                    action_name="Gerenciar",
                ),
            ]
        )

    unique_modules = {}

    for module in modules:
        unique_modules[module["slug"]] = module

    unique_permissions = {}

    for permission in permissions:
        unique_permissions[permission["code"]] = permission

    return list(unique_modules.values()), list(unique_permissions.values())


def map_access_user_to_payload(row):
    username = normalize_text(
        get_row_value(row, "usuNome")
    )

    group_name = normalize_text(
        get_row_value(row, "usuGrupo")
    )

    full_name = normalize_text(
        get_row_value(row, "usuNomeCompleto")
    )

    legacy_id = get_row_value(row, "usuarioID", None)

    user_type = infer_user_type(row)

    legacy_user = {
        "legacy_id": legacy_id,
        "username": username,
        "legacy_username": username,
        "full_name": full_name or username,
        "email": None,
        "user_type": user_type,
        "approval_limit": get_row_value(row, "usuAlcada", 0) or 0,
        "can_access_dashboard": is_yes(
            get_row_value(row, "usuPainel")
        ),
        "can_access_deductibles": is_yes(
            get_row_value(row, "usuDedutiveis")
        ),
        "legacy_group_name": group_name,
        "last_legacy_login_at": get_row_value(row, "usuLogadoEm", None),
    }

    groups = infer_groups(row)

    return {
        "legacy_user": legacy_user,
        "groups": groups,

        # The new SGOWEB authorization model does not trust legacy permissions.
        # Access only authenticates and provides user/group information.
        "modules": [],
        "permissions": [],
    }