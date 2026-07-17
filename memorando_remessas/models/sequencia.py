from django.db import models


class ShipmentMemoSequence(models.Model):
    key = models.CharField(
        max_length=50,
        unique=True,
        default="shipment_memo",
        db_column="chave",
        verbose_name="Chave",
    )

    current_value = models.PositiveBigIntegerField(
        default=0,
        db_column="valor_atual",
        verbose_name="Valor atual",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        db_column="atualizado_em",
        verbose_name="Atualizado em",
    )

    class Meta:
        db_table = "memorando_remessa_sequencias"
        verbose_name = "Sequência de memorando"
        verbose_name_plural = "Sequências de memorando"

    def __str__(self):
        return f"{self.key}: {self.current_value}"