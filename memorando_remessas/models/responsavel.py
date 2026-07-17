from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from accounts.models.choices import UserType
from memorando_remessas.models.memorando import ShipmentMemo


class ShipmentMemoResponsible(models.Model):
    id = models.BigAutoField(
        primary_key=True,
        db_column="id_memorando_responsavel",
    )

    shipment_memo = models.ForeignKey(
        ShipmentMemo,
        on_delete=models.CASCADE,
        related_name="responsible_links",
        db_column="id_memorando",
        verbose_name="Memorando",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="responsible_shipment_memos",
        db_column="id_usuario",
        verbose_name="Responsável",
    )

    is_primary = models.BooleanField(
        default=False,
        db_column="responsavel_principal",
        verbose_name="Responsável principal",
    )

    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="added_shipment_memo_responsibles",
        db_column="adicionado_por_id",
        verbose_name="Adicionado por",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_column="criado_em",
        verbose_name="Adicionado em",
    )

    class Meta:
        db_table = "memorando_remessa_responsaveis"
        verbose_name = "Responsável pelo memorando"
        verbose_name_plural = "Responsáveis pelos memorandos"
        ordering = [
            "-is_primary",
            "created_at",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "shipment_memo",
                    "user",
                ],
                name="uq_memorando_responsavel_usuario",
            ),
            models.UniqueConstraint(
                fields=[
                    "shipment_memo",
                ],
                condition=models.Q(is_primary=True),
                name="uq_memorando_responsavel_principal",
            ),
        ]

    def __str__(self):
        primary_label = "principal" if self.is_primary else "responsável"

        return (
            f"{self.shipment_memo} - "
            f"{self.user} ({primary_label})"
        )

    def clean(self):
        super().clean()

        if self.user_id:
            if not self.user.is_active:
                raise ValidationError({
                    "user": (
                        "O usuário selecionado está inativo."
                    )
                })

            if self.user.user_type != UserType.EMPLOYEE:
                raise ValidationError({
                    "user": (
                        "Somente colaboradores podem ser responsáveis "
                        "por memorandos de remessa."
                    )
                })

        if self.is_primary and self.shipment_memo_id:
            existing_primary = (
                ShipmentMemoResponsible.objects
                .filter(
                    shipment_memo_id=self.shipment_memo_id,
                    is_primary=True,
                )
                .exclude(pk=self.pk)
                .exists()
            )

            if existing_primary:
                raise ValidationError({
                    "is_primary": (
                        "Este memorando já possui um responsável principal."
                    )
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)