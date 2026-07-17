from django.conf import settings
from django.db import models

from memorando_remessas.models.choices import (
    ShipmentMemoHistoryAction,
)


class ShipmentMemoHistory(models.Model):
    id = models.BigAutoField(
        primary_key=True,
        db_column="id_memorando_historico",
    )

    shipment_memo = models.ForeignKey(
        "memorando_remessas.ShipmentMemo",
        on_delete=models.CASCADE,
        related_name="history_entries",
        db_column="id_memorando",
        verbose_name="Memorando",
    )

    action = models.CharField(
        max_length=30,
        choices=ShipmentMemoHistoryAction.choices,
        db_column="acao",
        verbose_name="Ação",
    )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="shipment_memo_history_entries",
        db_column="id_usuario",
        verbose_name="Usuário",
    )

    description = models.TextField(
        blank=True,
        default="",
        db_column="descricao",
        verbose_name="Descrição",
    )

    before_data = models.JSONField(
        blank=True,
        default=dict,
        db_column="dados_anteriores",
        verbose_name="Dados anteriores",
    )

    after_data = models.JSONField(
        blank=True,
        default=dict,
        db_column="dados_posteriores",
        verbose_name="Dados posteriores",
    )

    metadata = models.JSONField(
        blank=True,
        default=dict,
        db_column="metadados",
        verbose_name="Metadados",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_column="criado_em",
        verbose_name="Criado em",
    )

    class Meta:
        db_table = "memorando_remessa_historicos"
        verbose_name = "Histórico do memorando"
        verbose_name_plural = "Históricos dos memorandos"
        ordering = [
            "-created_at",
            "-id",
        ]
        indexes = [
            models.Index(
                fields=[
                    "shipment_memo",
                    "-created_at",
                ],
                name="memo_hist_mem_data_idx",
            ),
            models.Index(
                fields=[
                    "action",
                    "-created_at",
                ],
                name="memo_hist_acao_data_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.shipment_memo} - "
            f"{self.get_action_display()}"
        )