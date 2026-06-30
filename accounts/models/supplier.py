from django.core.exceptions import ValidationError
from django.db import models

from accounts.models.choices import UserType


class Supplier(models.Model):
    id = models.BigAutoField(
        primary_key=True,
        db_column="id_fornecedor",
    )

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        db_column="id_usuario",
        related_name="supplier_profile",
    )

    legacy_supplier_id = models.IntegerField(
        blank=True,
        null=True,
        db_column="fornecedor_origem_id",
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
        db_column="cnpj",
    )

    is_active = models.BooleanField(
        default=True,
        db_column="ativo",
    )

    class Meta:
        db_table = "fornecedores"
        verbose_name = "Supplier"
        verbose_name_plural = "Suppliers"
        ordering = ["trade_name", "legal_name"]

    def __str__(self):
        return self.trade_name or self.legal_name or self.user.name

    def clean(self):
        super().clean()

        if self.user.user_type != UserType.SUPPLIER:
            raise ValidationError({
                "user": "The linked user must be of type FORNECEDOR."
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)