from django.conf import settings
from django.db import models

from accounts.models.hub_menu_item import HubMenuItem


class UserHubMenuItemFavorite(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="hub_menu_item_favorites",
        verbose_name="Usuário",
    )

    menu_item = models.ForeignKey(
        HubMenuItem,
        on_delete=models.CASCADE,
        related_name="user_favorites",
        verbose_name="Funcionalidade",
    )

    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Ordem",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Criado em",
    )

    class Meta:
        db_table = "hub_usuario_item_menu_favoritos"
        verbose_name = "Funcionalidade favorita do usuário"
        verbose_name_plural = "Funcionalidades favoritas dos usuários"
        ordering = ["order", "menu_item__order", "menu_item__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "menu_item"],
                name="unique_user_hub_menu_item_favorite",
            )
        ]

    def __str__(self):
        return f"{self.user} - {self.menu_item}"
