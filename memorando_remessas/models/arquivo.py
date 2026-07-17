import uuid
from pathlib import Path

from django.conf import settings
from django.db import models


def shipment_memo_file_upload_to(
    instance,
    filename: str,
) -> str:
    extension = Path(filename).suffix.lower()

    memo_id = (
        instance.shipment_memo_id
        or "novo"
    )

    generated_name = (
        f"{uuid.uuid4().hex}{extension}"
    )

    return (
        f"memorando_remessas/"
        f"{memo_id}/"
        f"{generated_name}"
    )


class ShipmentMemoFile(models.Model):
    id = models.BigAutoField(
        primary_key=True,
        db_column="id_memorando_arquivo",
    )

    shipment_memo = models.ForeignKey(
        "memorando_remessas.ShipmentMemo",
        on_delete=models.CASCADE,
        related_name="files",
        db_column="id_memorando",
        verbose_name="Memorando",
    )

    file = models.FileField(
        upload_to=shipment_memo_file_upload_to,
        max_length=500,
        db_column="arquivo",
        verbose_name="Arquivo",
    )

    original_name = models.CharField(
        max_length=255,
        db_column="nome_original",
        verbose_name="Nome original",
    )

    content_type = models.CharField(
        max_length=150,
        blank=True,
        default="",
        db_column="tipo_conteudo",
        verbose_name="Tipo de conteúdo",
    )

    size = models.PositiveBigIntegerField(
        default=0,
        db_column="tamanho",
        verbose_name="Tamanho em bytes",
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_shipment_memo_files",
        db_column="enviado_por_id",
        verbose_name="Enviado por",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_column="criado_em",
        verbose_name="Enviado em",
    )

    class Meta:
        db_table = "memorando_remessa_arquivos"
        verbose_name = "Arquivo do memorando"
        verbose_name_plural = "Arquivos dos memorandos"
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
                name="memo_arq_mem_data_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.shipment_memo} - "
            f"{self.original_name}"
        )

    def save(self, *args, **kwargs):
        self.original_name = (
            Path(self.original_name).name.strip()
        )

        self.content_type = (
            self.content_type or ""
        ).strip()

        self.full_clean()

        super().save(
            *args,
            **kwargs,
        )