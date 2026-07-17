from django.conf import settings
from django.db import models

from accounts.models.hub_module import HubModule


class UserHubModuleFavorite(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="hub_module_favorites",
        verbose_name="Usuário",
    )

    module = models.ForeignKey(
        HubModule,
        on_delete=models.CASCADE,
        related_name="user_favorites",
        verbose_name="Módulo",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Criado em",
    )

    class Meta:
        db_table = "hub_usuario_modulo_favoritos"
        verbose_name = "Favorito de módulo do usuário"
        verbose_name_plural = "Favoritos de módulos dos usuários"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "module"],
                name="unique_user_hub_module_favorite",
            )
        ]

    def __str__(self):
        return f"{self.user} - {self.module}"