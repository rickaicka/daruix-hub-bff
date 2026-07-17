from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models

from memorando_remessas.models.choices import (
    ShipmentMemoStatus,
    WorkSource,
)


class ShipmentMemo(models.Model):
    id = models.BigAutoField(
        primary_key=True,
        db_column="id_memorando",
    )

    code = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        editable=False,
        db_column="codigo",
        verbose_name="Código",
        help_text=(
            "Código gerado pelo sistema. "
            "Exemplo: MR21065-001."
        ),
    )

    sequence_number = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        editable=False,
        db_column="numero_sequencial",
        verbose_name="Número sequencial",
    )

    revision = models.PositiveSmallIntegerField(
        default=1,
        db_column="revisao",
        verbose_name="Revisão",
    )

    revised_from = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="generated_revisions",
        null=True,
        blank=True,
        db_column="revisado_de_id",
        verbose_name="Revisado a partir de",
        help_text=(
            "Memorando anterior que originou esta revisão. "
            "Fica vazio na primeira versão."
        ),
    )

    status = models.CharField(
        max_length=30,
        choices=ShipmentMemoStatus.choices,
        default=ShipmentMemoStatus.DRAFT,
        db_index=True,
        db_column="status",
        verbose_name="Status",
    )

    work_source = models.CharField(
        max_length=20,
        choices=WorkSource.choices,
        default=WorkSource.ACCESS,
        db_column="origem_obra",
        verbose_name="Origem da obra",
    )

    legacy_work_id = models.IntegerField(
        null=True,
        blank=True,
        db_column="obra_origem_id",
        verbose_name="ID da obra no legado",
    )

    legacy_proposal_id = models.IntegerField(
        null=True,
        blank=True,
        db_column="proposta_origem_id",
        verbose_name="ID da proposta no legado",
    )

    cost_center = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_column="centro_custo",
        verbose_name="Centro de custo",
    )

    work_name = models.CharField(
        max_length=180,
        blank=True,
        default="",
        db_column="nome_obra",
        verbose_name="Nome da obra",
    )

    client_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_column="nome_cliente",
        verbose_name="Cliente",
    )

    client_document = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_column="documento_cliente",
        verbose_name="Documento do cliente",
    )

    shipping_date = models.DateField(
        null=True,
        blank=True,
        db_column="data_remessa",
        verbose_name="Data da remessa",
    )

    subject = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_column="assunto",
        verbose_name="Assunto",
    )

    attention_to = models.CharField(
        max_length=180,
        blank=True,
        default="",
        db_column="aos_cuidados_de",
        verbose_name="Aos cuidados de",
    )

    recipient_emails = models.JSONField(
        default=list,
        blank=True,
        db_column="emails_destinatarios",
        verbose_name="E-mails dos destinatários",
        help_text=(
            "Lista dos endereços que receberão diretamente "
            "o memorando."
        ),
    )

    cc_emails = models.JSONField(
        default=list,
        blank=True,
        db_column="emails_copia",
        verbose_name="E-mails em cópia",
        help_text=(
            "Lista dos endereços que receberão uma cópia "
            "do memorando."
        ),
    )

    notes = models.TextField(
        blank=True,
        default="",
        db_column="observacoes",
        verbose_name="Observações",
    )

    options = models.ManyToManyField(
        "memorando_remessas.ShipmentMemoOption",
        through=(
            "memorando_remessas."
            "ShipmentMemoOptionSelection"
        ),
        related_name="shipment_memos",
        blank=True,
        verbose_name="Opções selecionadas",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_shipment_memos",
        db_column="criado_por_id",
        verbose_name="Criado por",
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_shipment_memos",
        db_column="atualizado_por_id",
        verbose_name="Atualizado por",
    )

    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sent_shipment_memos",
        null=True,
        blank=True,
        db_column="enviado_por_id",
        verbose_name="Enviado por",
    )

    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        db_column="enviado_em",
        verbose_name="Enviado em",
    )

    last_send_error = models.TextField(
        blank=True,
        default="",
        db_column="ultimo_erro_envio",
        verbose_name="Último erro de envio",
    )

    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cancelled_shipment_memos",
        null=True,
        blank=True,
        db_column="cancelado_por_id",
        verbose_name="Cancelado por",
    )

    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
        db_column="cancelado_em",
        verbose_name="Cancelado em",
    )

    cancellation_reason = models.TextField(
        blank=True,
        default="",
        db_column="motivo_cancelamento",
        verbose_name="Motivo do cancelamento",
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
        db_table = "memorandos_remessa"
        verbose_name = "Memorando de remessa"
        verbose_name_plural = "Memorandos de remessa"
        ordering = [
            "-created_at",
        ]
        indexes = [
            models.Index(
                fields=["status", "-created_at"],
                name="memo_status_created_idx",
            ),
            models.Index(
                fields=["legacy_work_id"],
                name="memo_legacy_work_idx",
            ),
            models.Index(
                fields=["cost_center"],
                name="memo_cost_center_idx",
            ),
            models.Index(
                fields=["shipping_date"],
                name="memo_shipping_date_idx",
            ),
            models.Index(
                fields=["code"],
                name="memo_code_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(revision__gte=1),
                name="memo_revision_gte_1",
            ),
            models.UniqueConstraint(
                fields=[
                    "code",
                    "revision",
                ],
                condition=models.Q(
                    code__isnull=False,
                ),
                name="uq_memo_codigo_revisao",
            ),
        ]

    def __str__(self):
        if self.code:
            identification = (
                f"{self.code} - Rev. {self.revision}"
            )
        else:
            identification = (
                f"Memorando #{self.pk or 'novo'}"
            )

        if self.work_name:
            return f"{identification} - {self.work_name}"

        return identification

    @staticmethod
    def _normalize_email_list(
        values,
        *,
        field_name: str,
    ) -> list[str]:
        if values in (None, ""):
            return []

        if not isinstance(values, list):
            raise ValidationError({
                field_name: (
                    "O valor deve ser uma lista de endereços "
                    "de e-mail."
                )
            })

        normalized_emails: list[str] = []
        invalid_emails: list[str] = []

        for value in values:
            email = str(value or "").strip().lower()

            if not email:
                continue

            try:
                validate_email(email)
            except ValidationError:
                invalid_emails.append(email)
                continue

            if email not in normalized_emails:
                normalized_emails.append(email)

        if invalid_emails:
            raise ValidationError({
                field_name: (
                    "Foram informados endereços de e-mail "
                    f"inválidos: {invalid_emails}"
                )
            })

        return normalized_emails

    def clean(self):
        super().clean()

        errors = {}

        try:
            self.recipient_emails = self._normalize_email_list(
                self.recipient_emails,
                field_name="recipient_emails",
            )
        except ValidationError as error:
            errors.update(
                getattr(
                    error,
                    "message_dict",
                    {
                        "recipient_emails": error.messages,
                    },
                )
            )

        try:
            self.cc_emails = self._normalize_email_list(
                self.cc_emails,
                field_name="cc_emails",
            )
        except ValidationError as error:
            errors.update(
                getattr(
                    error,
                    "message_dict",
                    {
                        "cc_emails": error.messages,
                    },
                )
            )

        if not errors:
            recipient_set = set(self.recipient_emails)

            self.cc_emails = [
                email
                for email in self.cc_emails
                if email not in recipient_set
            ]

        if self.pk and self.revised_from_id == self.pk:
            errors["revised_from"] = (
                "Um memorando não pode ser uma revisão dele mesmo."
            )

        if self.revised_from_id and self.revision <= 1:
            errors["revision"] = (
                "Uma revisão originada de outro memorando "
                "deve possuir número maior que 1."
            )

        if self.status == ShipmentMemoStatus.SENT:
            if not self.sent_by:
                errors["sent_by"] = (
                    "O usuário responsável pelo envio "
                    "deve ser informado."
                )

            if not self.sent_at:
                errors["sent_at"] = (
                    "A data e hora do envio devem ser informadas."
                )

        if self.status == ShipmentMemoStatus.CANCELLED:
            if not self.cancelled_by:
                errors["cancelled_by"] = (
                    "O usuário responsável pelo cancelamento "
                    "deve ser informado."
                )

            if not self.cancelled_at:
                errors["cancelled_at"] = (
                    "A data e hora do cancelamento "
                    "devem ser informadas."
                )

            if not self.cancellation_reason.strip():
                errors["cancellation_reason"] = (
                    "O motivo do cancelamento deve ser informado."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()

        super().save(
            *args,
            **kwargs,
        )

    @property
    def is_draft(self):
        return self.status == ShipmentMemoStatus.DRAFT

    @property
    def is_processing(self):
        return self.status == ShipmentMemoStatus.PROCESSING

    @property
    def is_sent(self):
        return self.status == ShipmentMemoStatus.SENT

    @property
    def is_failed(self):
        return self.status == ShipmentMemoStatus.FAILED

    @property
    def is_cancelled(self):
        return self.status == ShipmentMemoStatus.CANCELLED

    @property
    def can_be_sent(self):
        return self.status in {
            ShipmentMemoStatus.DRAFT,
            ShipmentMemoStatus.FAILED,
        }

    @property
    def is_editable(self):
        return self.status == ShipmentMemoStatus.DRAFT