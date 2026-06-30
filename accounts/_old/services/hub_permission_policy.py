"""
Política oficial de permissões do Daruix Hub.

Este arquivo define quais módulos e ações são considerados válidos
no sistema novo.

Objetivo:
- evitar importar a granularidade antiga do Access;
- impedir que permissões de forms, botões, campos e tabelas antigas
  apareçam no login;
- manter o permissionamento baseado em ações de negócio.
"""


HUB_MODULE_ACTIONS = {
    "dashboard": {
        "view",
    },

    "deductibles": {
        "view",
    },

    "purchase_orders": {
        "view",
        "create",
        "update",
        "delete",
        "approve",
        "export",
    },

    "admin": {
        "view",
        "manage",
    },
}


HUB_ACTION_NAMES = {
    "view": "Visualizar",
    "create": "Criar",
    "update": "Alterar",
    "delete": "Excluir",
    "approve": "Aprovar",
    "cancel": "Cancelar",
    "export": "Exportar",
    "manage": "Gerenciar",
}


HUB_MODULE_NAMES = {
    "dashboard": "Painel",
    "deductibles": "Dedutíveis",
    "purchase_orders": "Ordens de Compra",
    "admin": "Administração",
}


def get_allowed_modules():
    """
    Retorna os slugs dos módulos aceitos pelo Hub moderno.
    """

    return set(HUB_MODULE_ACTIONS.keys())


def get_allowed_actions_for_module(module_slug):
    """
    Retorna as ações permitidas para um módulo.
    """

    return HUB_MODULE_ACTIONS.get(module_slug, set())


def is_allowed_hub_module(module_slug):
    """
    Verifica se o módulo faz parte da política moderna do Hub.
    """

    return module_slug in HUB_MODULE_ACTIONS


def is_allowed_hub_action(module_slug, action):
    """
    Verifica se uma ação é permitida dentro de um módulo.
    """

    return action in HUB_MODULE_ACTIONS.get(module_slug, set())


def parse_permission_code(code):
    """
    Quebra uma permissão no formato:

    <tipo_usuario>.<modulo>.<acao>

    Exemplo:
    employee.purchase_orders.view
    """

    if not code:
        return None

    parts = str(code).split(".")

    if len(parts) != 3:
        return None

    user_type_slug, module_slug, action = parts

    if not user_type_slug or not module_slug or not action:
        return None

    return {
        "user_type_slug": user_type_slug,
        "module_slug": module_slug,
        "action": action,
    }


def is_allowed_permission_code(code):
    """
    Verifica se uma permissão está dentro da política moderna do Hub.

    Exemplo permitido:
    employee.purchase_orders.view

    Exemplo bloqueado:
    employee.acompemail.approve
    """

    parsed = parse_permission_code(code)

    if not parsed:
        return False

    return is_allowed_hub_action(
        module_slug=parsed["module_slug"],
        action=parsed["action"],
    )


def get_permission_action(code):
    """
    Retorna apenas a ação de uma permissão.

    Exemplo:
    employee.purchase_orders.approve -> approve
    """

    parsed = parse_permission_code(code)

    if not parsed:
        return None

    return parsed["action"]


def get_permission_module_slug(code):
    """
    Retorna apenas o módulo de uma permissão.

    Exemplo:
    employee.purchase_orders.approve -> purchase_orders
    """

    parsed = parse_permission_code(code)

    if not parsed:
        return None

    return parsed["module_slug"]