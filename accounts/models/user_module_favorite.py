"""Compatibilidade temporária com imports antigos.

O favorito agora pertence a uma funcionalidade do menu, e não ao módulo.
Remova este arquivo depois que todos os imports antigos forem atualizados.
"""

from accounts.models.user_menu_item_favorite import UserHubMenuItemFavorite


UserHubModuleFavorite = UserHubMenuItemFavorite

__all__ = ["UserHubMenuItemFavorite", "UserHubModuleFavorite"]
