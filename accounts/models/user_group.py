from django.db import models

from accounts.models.choices import UserType


class UserGroup(models.Model):
    id = models.BigAutoField(
        primary_key=True,
        db_column="id_grupo",
    )

    user_type = models.CharField(
        max_length=20,
        choices=UserType.choices,
        db_column="tipo_usuario",
    )

    name = models.CharField(
        max_length=50,
        db_column="nome_grupo",
    )

    description = models.TextField(
        blank=True,
        null=True,
        db_column="descricao",
    )

    is_active = models.BooleanField(
        default=True,
        db_column="ativo",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_column="criado_em",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        db_column="atualizado_em",
    )

    class Meta:
        db_table = "grupos_usuario"
        verbose_name = "User group"
        verbose_name_plural = "User groups"
        ordering = ["user_type", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user_type", "name"],
                name="uq_user_group_type_name",
            )
        ]

    def __str__(self):
        return f"{self.user_type} | {self.name}"