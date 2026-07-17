from django.conf import settings
from django.db import models

from memorando_remessas.models.choices import (
    ShipmentMemoOptionType,
)
from memorando_remessas.models.memorando import ShipmentMemo


class ShipmentMemoOption(models.Model):
    id = models.BigAutoField(
        primary_key=True,
        db_column="id_memorando_opcao",
    )

    option_type = models.CharField(
        max_length=20,
        choices=ShipmentMemoOptionType.choices,
        db_column="tipo_opcao",
        verbose_name="Tipo",
    )

    code = models.SlugField(
        max_length=80,
        db_column="codigo",
        verbose_name="Código",
        help_text=(
            "Identificador estável usado pela API. "
            "Exemplo: carta, documento, aprovacao."
        ),
    )

    name = models.CharField(
        max_length=150,
        db_column="nome",
        verbose_name="Nome",
    )

    description = models.TextField(
        blank=True,
        default="",
        db_column="descricao",
        verbose_name="Descrição",
    )

    order = models.PositiveIntegerField(
        default=0,
        db_column="ordem",
        verbose_name="Ordem",
    )

    is_active = models.BooleanField(
        default=True,
        db_column="ativo",
        verbose_name="Ativo",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_column="criado_em",
        verbose_name="Criado em",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        db_column="atualizado_em",
        verbose_name="Atualizado em",
    )

    class Meta:
        db_table = "memorando_remessa_opcoes"
        verbose_name = "Opção de memorando"
        verbose_name_plural = "Opções de memorando"
        ordering = [
            "option_type",
            "order",
            "name",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "option_type",
                    "code",
                ],
                name="uq_memorando_opcao_tipo_codigo",
            ),
        ]
        indexes = [
            models.Index(
                fields=[
                    "option_type",
                    "is_active",
                    "order",
                ],
                name="memo_opcao_tipo_ativo_idx",
            ),
        ]

    def __str__(self):
        option_type = self.get_option_type_display()

        return f"{option_type} - {self.name}"

    def save(self, *args, **kwargs):
        self.code = self.code.strip().lower()
        self.name = self.name.strip()
        self.full_clean()

        super().save(*args, **kwargs)


class ShipmentMemoOptionSelection(models.Model):
    id = models.BigAutoField(
        primary_key=True,
        db_column="id_memorando_opcao_selecionada",
    )

    shipment_memo = models.ForeignKey(
        ShipmentMemo,
        on_delete=models.CASCADE,
        related_name="option_selections",
        db_column="id_memorando",
        verbose_name="Memorando",
    )

    option = models.ForeignKey(
        ShipmentMemoOption,
        on_delete=models.PROTECT,
        related_name="memo_selections",
        db_column="id_opcao",
        verbose_name="Opção",
    )

    selected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="selected_shipment_memo_options",
        db_column="selecionado_por_id",
        verbose_name="Selecionado por",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_column="criado_em",
        verbose_name="Selecionado em",
    )

    class Meta:
        db_table = "memorando_remessa_opcoes_selecionadas"
        verbose_name = "Opção selecionada do memorando"
        verbose_name_plural = "Opções selecionadas dos memorandos"
        ordering = [
            "option__option_type",
            "option__order",
            "option__name",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "shipment_memo",
                    "option",
                ],
                name="uq_memorando_opcao_selecionada",
            ),
        ]
        indexes = [
            models.Index(
                fields=["shipment_memo"],
                name="memo_opcao_selec_mem_idx",
            ),
            models.Index(
                fields=["option"],
                name="memo_opcao_selec_opc_idx",
            ),
        ]

    def __str__(self):
        return f"{self.shipment_memo} - {self.option}"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)