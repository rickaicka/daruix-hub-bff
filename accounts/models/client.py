from django.core.exceptions import ValidationError
from django.db import models

from accounts.models.choices import ClientGroup, UserType


class Client(models.Model):
    id = models.BigAutoField(
        primary_key=True,
        db_column="id_cliente",
    )

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        db_column="id_usuario",
        related_name="client_profile",
    )

    client_group = models.CharField(
        max_length=20,
        choices=ClientGroup.choices,
        db_column="grupo_cliente",
    )

    parent_client = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        db_column="cliente_origem_id",
        related_name="operational_clients",
        blank=True,
        null=True,
        help_text="Board/origin client related to this operational client.",
    )

    trade_name = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        db_column="nome_fantasia",
    )

    legal_name = models.CharField(
        max_length=180,
        blank=True,
        null=True,
        db_column="razao_social",
    )

    document = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        db_column="cnpj_cpf",
    )

    is_active = models.BooleanField(
        default=True,
        db_column="ativo",
    )

    class Meta:
        db_table = "clientes"
        verbose_name = "Client"
        verbose_name_plural = "Clients"
        ordering = ["trade_name", "legal_name"]

    def __str__(self):
        return self.trade_name or self.legal_name or self.user.name

    def clean(self):
        super().clean()

        if self.user.user_type != UserType.CLIENT:
            raise ValidationError({
                "user": "The linked user must be of type CLIENTE."
            })

        if self.client_group == ClientGroup.BOARD and self.parent_client:
            raise ValidationError({
                "parent_client": "A board client should not have a parent client."
            })

        if self.parent_client and self.parent_client.client_group != ClientGroup.BOARD:
            raise ValidationError({
                "parent_client": "The parent client must be a board client."
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)