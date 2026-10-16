from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Max, Q

from .choices import (
    BudgetSheetStatus,
    BudgetSheetItemType,
    BudgetStageLegacySource,
    CompositionItemType,
    CompositionStatus,
    DataOrigin,
    ImportResource,
    ImportStatus,
    SupplyType,
)


class Supply(models.Model):
    origin = models.CharField(
        max_length=10,
        choices=DataOrigin.choices,
        default=DataOrigin.HUB,
        db_index=True,
    )
    legacy_table = models.CharField(max_length=100, blank=True)
    legacy_id = models.BigIntegerField(null=True, blank=True)
    description = models.CharField(max_length=500, db_index=True)
    supply_type = models.CharField(
        max_length=20,
        choices=SupplyType.choices,
        default=SupplyType.OTHER,
    )
    unit = models.CharField(max_length=30, blank=True)
    full_description = models.TextField(
        blank=True,
        default="",
        verbose_name="Descrição completa",
    )
    unit_measure = models.ForeignKey(
        "UnitMeasure",
        on_delete=models.PROTECT,
        related_name="supplies",
        null=True,
        blank=True,
        verbose_name="Unidade de medida",
    )
    material_group = models.ForeignKey(
        "MaterialGroup",
        on_delete=models.PROTECT,
        related_name="supplies",
        null=True,
        blank=True,
        verbose_name="Grupo de material",
    )
    specification = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    legacy_payload = models.JSONField(default=dict, blank=True)
    legacy_payload_hash = models.CharField(max_length=64, blank=True)
    imported_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supplies_created",
        verbose_name="Criado por",
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supplies_updated",
        verbose_name="Editado por",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "budgeting_supply"
        verbose_name = "insumo"
        verbose_name_plural = "insumos"
        ordering = ("description", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("origin", "legacy_table", "legacy_id"),
                condition=Q(legacy_id__isnull=False),
                name="uq_supply_legacy_identity",
            ),
        ]
        indexes = [
            models.Index(
                fields=("is_active", "description"),
                name="supply_active_desc_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.description


class UnitMeasure(models.Model):
    legacy_id = models.PositiveIntegerField(
        unique=True,
        verbose_name="ID no legado",
    )
    nome = models.CharField(
        max_length=50,
    )
    sigla = models.CharField(
        max_length=10,
        db_index=True,
    )
    ativo = models.BooleanField(
        default=True,
        db_index=True,
    )
    criado_em = models.DateTimeField(
        auto_now_add=True,
    )
    atualizado_em = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "composicao_servico_unidade_medida"
        ordering = ("legacy_id", "nome", "id")
        verbose_name = "Unidade de medida"
        verbose_name_plural = "Unidades de medida"
        indexes = [
            models.Index(
                fields=["ativo", "sigla"],
                name="unid_ativo_sigla_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sigla} - {self.nome}"


class MaterialGroup(models.Model):
    legacy_id = models.PositiveIntegerField(
        db_index=True,
        verbose_name="ID no legado",
    )
    nome = models.CharField(
        max_length=255,
        db_index=True,
    )
    ativo = models.BooleanField(
        default=True,
        db_index=True,
    )
    criado_em = models.DateTimeField(
        auto_now_add=True,
    )
    atualizado_em = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "composicao_servico_grupo_material"
        ordering = ("legacy_id", "nome", "id")
        verbose_name = "Grupo de material"
        verbose_name_plural = "Grupos de materiais"
        indexes = [
            models.Index(
                fields=["ativo", "nome"],
                name="grupo_ativo_nome_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("legacy_id", "nome"),
                name="uq_material_group_legacy_name",
            ),
        ]

    def __str__(self) -> str:
        return self.nome

class BudgetStageCatalog(models.Model):
    origin = models.CharField(
        max_length=10,
        choices=DataOrigin.choices,
        default=DataOrigin.HUB,
        db_index=True,
    )
    legacy_source = models.CharField(
        max_length=50,
        choices=BudgetStageLegacySource.choices,
        blank=True,
        default="",
        db_index=True,
    )
    legacy_id = models.BigIntegerField(
        null=True,
        blank=True,
        db_index=True,
    )
    legacy_key = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )
    code = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_index=True,
    )
    name = models.CharField(
        max_length=255,
        db_index=True,
    )

    # Classificação informativa trazida do legado.
    # Não restringe a etapa a um departamento do Hub.
    legacy_category = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_index=True,
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
    )
    legacy_payload = models.JSONField(
        default=dict,
        blank=True,
    )
    legacy_payload_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )
    imported_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "budgeting_stage_catalog"
        verbose_name = "etapa de orçamento"
        verbose_name_plural = "etapas de orçamento"
        ordering = ("name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "origin",
                    "legacy_source",
                    "legacy_id",
                ),
                condition=Q(legacy_id__isnull=False),
                name="uq_stage_catalog_legacy_identity",
            ),
            models.UniqueConstraint(
                fields=("legacy_key",),
                condition=~Q(legacy_key=""),
                name="uq_stage_catalog_legacy_key",
            ),
            models.CheckConstraint(
                condition=(
                    (
                        Q(
                            origin=DataOrigin.LEGACY,
                            legacy_id__isnull=False,
                        )
                        & ~Q(legacy_source="")
                        & ~Q(legacy_key="")
                    )
                    | Q(
                        origin=DataOrigin.HUB,
                        legacy_id__isnull=True,
                        legacy_source="",
                        legacy_key="",
                    )
                ),
                name="ck_stage_catalog_origin_identity",
            ),
        ]
        indexes = [
            models.Index(
                fields=("is_active", "name"),
                name="stage_catalog_active_name_idx",
            ),
        ]

    def __str__(self) -> str:
        if self.code:
            return f"{self.code} - {self.name}"

        return self.name

class BudgetSheet(models.Model):
    revision_root = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="revisions",
        null=True,
        blank=True,
        verbose_name="Planilha original",
    )
    previous_revision = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        related_name="next_revision",
        null=True,
        blank=True,
        verbose_name="Revisão anterior",
    )
    revision_reason = models.TextField(
        blank=True,
        default="",
        verbose_name="Motivo da revisão",
    )
    proposal = models.ForeignKey(
        "commercial.Proposal",
        on_delete=models.PROTECT,
        related_name="budget_sheets",
        null=True,
        blank=True,
        verbose_name="Proposta/PC",
    )
    party = models.ForeignKey(
        "commercial.Party",
        on_delete=models.PROTECT,
        related_name="budget_sheets",
        null=True,
        blank=True,
        verbose_name="Cliente/interessado",
    )
    department = models.ForeignKey(
        "commercial.Department",
        on_delete=models.PROTECT,
        related_name="budget_sheets",
        null=True,
        blank=True,
        verbose_name="Departamento responsável",
    )
    number = models.CharField(
        max_length=50,
        verbose_name="Número do orçamento",
    )
    proposal_sequence = models.PositiveIntegerField(
        default=0,
        verbose_name="Sequência da planilha no PC",
        help_text=(
            "Identifica planilhas independentes vinculadas à mesma proposta/PC. "
            "Cada sequência possui seu próprio histórico de revisões."
        ),
    )
    revision = models.PositiveIntegerField(
        default=0,
        verbose_name="Revisão",
    )
    reference_date = models.DateField(
        default=timezone.localdate,
        verbose_name="Data",
    )
    considerations = models.TextField(
        blank=True,
        default="",
        verbose_name="Considerações do orçamento",
    )
    bdi_percentage = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        default=Decimal("0"),
        verbose_name="BDI calculado (%)",
        help_text=(
            "Resultado calculado/cache da memória BDI desta revisão. "
            "Não deve ser editado diretamente pela API."
        ),
    )
    bdi_configuration = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Memória de cálculo BDI",
    )
    di_configuration = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Memória de despesas indiretas",
    )
    status = models.CharField(
        max_length=20,
        choices=BudgetSheetStatus.choices,
        default=BudgetSheetStatus.DRAFT,
        db_index=True,
    )
    total_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
        verbose_name="Total geral",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="budget_sheets_created",
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="budget_sheets_updated",
        null=True,
        blank=True,
    )
    finalized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="budget_sheets_finalized",
        null=True,
        blank=True,
    )
    finalized_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "budgeting_sheet"
        verbose_name = "planilha de orçamento"
        verbose_name_plural = "planilhas de orçamento"
        ordering = ("-reference_date", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("proposal", "proposal_sequence", "revision"),
                condition=Q(proposal__isnull=False),
                name="uq_budget_sheet_proposal_sequence_revision",
            ),
            models.UniqueConstraint(
                fields=("number", "revision"),
                name="uq_budget_sheet_number_revision",
            ),
            models.CheckConstraint(
                condition=Q(revision__gte=0),
                name="ck_budget_sheet_revision_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(total_amount__gte=0),
                name="ck_budget_sheet_total_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(bdi_percentage__gte=0),
                name="ck_budget_sheet_bdi_gte_0",
            ),
        ]
        indexes = [
            models.Index(
                fields=("status", "reference_date"),
                name="budget_sheet_status_date_idx",
            ),
            models.Index(
                fields=("revision_root", "revision"),
                name="budget_revision_group_idx",
            ),
        ]

    @staticmethod
    def build_number(
        proposal_code: str,
        proposal_sequence: int,
    ) -> str:
        normalized_code = (
            str(proposal_code or "")
            .strip()
            .upper()
        )

        if normalized_code.startswith("PC"):
            normalized_code = normalized_code[2:]

        return f"{normalized_code}-{proposal_sequence:02d}"

    def clean(self) -> None:
        super().clean()

        errors = {}

        if self.pk and self.revision_root_id == self.pk:
            errors["revision_root"] = (
                "A planilha não pode ser a própria raiz de revisão."
            )

        if self.pk and self.previous_revision_id == self.pk:
            errors["previous_revision"] = (
                "A planilha não pode apontar para si mesma como revisão anterior."
            )

        if self.previous_revision_id:
            previous_root_id = (
                self.previous_revision.revision_root_id
                or self.previous_revision_id
            )

            if self.revision_root_id != previous_root_id:
                errors["revision_root"] = (
                    "A raiz deve ser a mesma da revisão anterior."
                )

            if self.revision <= self.previous_revision.revision:
                errors["revision"] = (
                    "A revisão deve ser posterior à planilha anterior."
                )

            if self.proposal_sequence != self.previous_revision.proposal_sequence:
                errors["proposal_sequence"] = (
                    "A revisão deve pertencer à mesma planilha de origem."
                )

        if self.proposal_id:
            if (
                self.party_id
                and self.party_id != self.proposal.party_id
            ):
                errors["party"] = (
                    "O cliente deve ser o mesmo da proposta selecionada."
                )

            if (
                self.department_id
                and self.proposal.department_id
                and self.department_id
                != self.proposal.department_id
            ):
                errors["department"] = (
                    "O departamento deve ser o mesmo da proposta selecionada."
                )

        if not self.proposal_id and not self.number.strip():
            errors["number"] = (
                "Informe o número quando a planilha não estiver "
                "vinculada a uma proposta."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.proposal_id:
            # Fora da API (admin, shell, testes), também evita transformar uma
            # segunda planilha do mesmo PC em revisão por falta de sequência.
            # A API faz esta alocação sob lock para garantir concorrência.
            if (
                self._state.adding
                and self.revision == 0
                and self.revision_root_id is None
                and self.previous_revision_id is None
                and BudgetSheet.objects.filter(
                    proposal_id=self.proposal_id,
                    proposal_sequence=self.proposal_sequence,
                    revision=0,
                    revision_root__isnull=True,
                ).exists()
            ):
                current_max = (
                    BudgetSheet.objects
                    .filter(
                        proposal_id=self.proposal_id,
                        revision=0,
                        revision_root__isnull=True,
                    )
                    .aggregate(value=Max("proposal_sequence"))["value"]
                )
                self.proposal_sequence = (current_max + 1) if current_max is not None else 0

            if not self.party_id:
                self.party_id = self.proposal.party_id

            if (
                not self.department_id
                and self.proposal.department_id
            ):
                self.department_id = self.proposal.department_id

            self.number = self.build_number(
                self.proposal.code,
                self.proposal_sequence,
            )

        self.full_clean()

        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.number

    @property
    def is_editable(self) -> bool:
        return self.status == BudgetSheetStatus.DRAFT

    @property
    def revision_group_root_id(self) -> int | None:
        return self.revision_root_id or self.pk

class BudgetSheetStage(models.Model):
    budget_sheet = models.ForeignKey(
        BudgetSheet,
        on_delete=models.CASCADE,
        related_name="stages",
        verbose_name="Planilha de orçamento",
    )
    stage = models.ForeignKey(
        BudgetStageCatalog,
        on_delete=models.PROTECT,
        related_name="budget_sheet_usages",
        verbose_name="Etapa",
    )
    order = models.PositiveIntegerField(
        verbose_name="Ordem",
    )
    name_snapshot = models.CharField(
        max_length=255,
        verbose_name="Nome utilizado no orçamento",
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Observações",
    )
    subtotal = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "budgeting_sheet_stage"
        verbose_name = "etapa da planilha"
        verbose_name_plural = "etapas da planilha"
        ordering = ("order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("budget_sheet", "stage"),
                name="uq_budget_sheet_stage",
            ),
            models.UniqueConstraint(
                fields=("budget_sheet", "order"),
                name="uq_budget_sheet_stage_order",
            ),
            models.CheckConstraint(
                condition=Q(order__gte=1),
                name="ck_budget_sheet_stage_order_gte_1",
            ),
            models.CheckConstraint(
                condition=Q(subtotal__gte=0),
                name="ck_budget_sheet_stage_subtotal_gte_0",
            ),
        ]
        indexes = [
            models.Index(
                fields=("budget_sheet", "order"),
                name="budget_sheet_stage_order_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()

        if (
            self.stage_id
            and not self.stage.is_active
            and self._state.adding
        ):
            raise ValidationError(
                {
                    "stage": (
                        "Uma etapa inativa não pode ser adicionada "
                        "ao orçamento."
                    )
                }
            )

    def save(self, *args, **kwargs):
        if self.stage_id and (
            self._state.adding
            or not self.name_snapshot
        ):
            self.name_snapshot = self.stage.name

        self.full_clean()

        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return (
            f"{self.budget_sheet.number} - "
            f"{self.order}. {self.name_snapshot}"
        )

class BudgetSheetStageItem(models.Model):
    budget_sheet_stage = models.ForeignKey(
        BudgetSheetStage,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Etapa da planilha",
    )
    item_type = models.CharField(
        max_length=25,
        choices=BudgetSheetItemType.choices,
        default=BudgetSheetItemType.SERVICE_COMPOSITION,
    )
    service_composition = models.ForeignKey(
        "ServiceComposition",
        on_delete=models.PROTECT,
        related_name="budget_sheet_items",
        null=True,
        blank=True,
    )
    supply = models.ForeignKey(
        "Supply",
        on_delete=models.PROTECT,
        related_name="budget_sheet_items",
        null=True,
        blank=True,
    )

    # Snapshots preservam o orçamento mesmo que o catálogo seja
    # renomeado ou ganhe uma nova versão futuramente.
    description_snapshot = models.CharField(
        max_length=500,
    )
    unit_snapshot = models.CharField(
        max_length=30,
        blank=True,
        default="",
    )
    # Snapshots financeiros e estruturais da composição utilizada no orçamento.
    # Estes campos pertencem à revisão da planilha e nunca devem ser
    # reconstruídos a partir de uma composição viva depois da finalização.
    composition_version_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Versão da composição utilizada",
    )
    material_unit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
        verbose_name="Custo unitário de material",
    )
    labor_unit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
        verbose_name="Custo unitário de mão de obra",
    )
    equipment_unit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
        verbose_name="Custo unitário de equipamento",
    )
    unit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
        verbose_name="Custo unitário total",
    )
    pricing_factor = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
        verbose_name="Fator efetivo de venda",
        help_text=(
            "Snapshot informativo de unit_price / unit_cost. "
            "Não substitui a parametrização formal de BDI/DI."
        ),
    )
    apply_bdi = models.BooleanField(
        default=False,
        verbose_name="Aplicar BDI",
        help_text=(
            "Quando verdadeiro em uma composição, o valor unitário da linha "
            "é recalculado com o BDI da planilha. Não altera os filhos do snapshot."
        ),
    )
    composition_snapshot = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Snapshot da composição e de seus componentes",
    )
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=Decimal("0"),
    )
    unit_price = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
    )
    unit_discount = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0"),
        verbose_name="Desconto unitário (R$)",
    )
    subtotal = models.DecimalField(
        max_digits=24,
        decimal_places=4,
        default=Decimal("0"),
    )
    order = models.PositiveIntegerField()
    notes = models.TextField(
        blank=True,
        default="",
    )

    # Identidade opcional para uma futura importação histórica.
    origin = models.CharField(
        max_length=10,
        choices=DataOrigin.choices,
        default=DataOrigin.HUB,
        db_index=True,
    )
    legacy_table = models.CharField(
        max_length=120,
        blank=True,
        default="",
    )
    legacy_id = models.BigIntegerField(
        null=True,
        blank=True,
        db_index=True,
    )
    legacy_payload = models.JSONField(
        default=dict,
        blank=True,
    )
    legacy_payload_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )
    imported_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "budgeting_sheet_stage_item"
        verbose_name = "item da etapa da planilha"
        verbose_name_plural = "itens da etapa da planilha"
        ordering = ("order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("budget_sheet_stage", "order"),
                name="uq_budget_stage_item_order",
            ),
            models.UniqueConstraint(
                fields=("legacy_table", "legacy_id"),
                condition=Q(legacy_id__isnull=False),
                name="uq_budget_stage_item_legacy",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        item_type=(
                            BudgetSheetItemType
                            .SERVICE_COMPOSITION
                        ),
                        service_composition__isnull=False,
                        supply__isnull=True,
                    )
                    | Q(
                        item_type=BudgetSheetItemType.SUPPLY,
                        service_composition__isnull=True,
                        supply__isnull=False,
                    )
                    | Q(
                        item_type=BudgetSheetItemType.FREE_TEXT,
                        service_composition__isnull=True,
                        supply__isnull=True,
                    )
                ),
                name="ck_budget_stage_item_reference",
            ),
            models.CheckConstraint(
                condition=Q(order__gte=1),
                name="ck_budget_stage_item_order_gte_1",
            ),
            models.CheckConstraint(
                condition=(
                    Q(quantity__gte=0)
                    & Q(unit_price__gte=0)
                    & Q(subtotal__gte=0)
                ),
                name="ck_budget_stage_item_values_gte_0",
            ),
            models.CheckConstraint(
                condition=(
                    Q(material_unit_cost__gte=0)
                    & Q(labor_unit_cost__gte=0)
                    & Q(equipment_unit_cost__gte=0)
                    & Q(unit_cost__gte=0)
                    & Q(pricing_factor__gte=0)
                ),
                name="ck_budget_stage_item_cost_snapshots_gte_0",
            ),
            models.CheckConstraint(
                condition=(
                    Q(item_type__in=[BudgetSheetItemType.SERVICE_COMPOSITION, BudgetSheetItemType.SUPPLY])
                    | Q(apply_bdi=False)
                ),
                name="ck_budget_stage_item_bdi_priced_item",
            ),
        ]
        indexes = [
            models.Index(
                fields=("budget_sheet_stage", "order"),
                name="budget_stage_item_order_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()

        errors = {}
        if Decimal(str(self.unit_discount or 0)) < 0:
            errors["unit_discount"] = "O desconto não pode ser negativo."


        if (
            self.item_type
            == BudgetSheetItemType.SERVICE_COMPOSITION
        ):
            if not self.service_composition_id:
                errors["service_composition"] = (
                    "A composição de serviço é obrigatória."
                )

            if self.supply_id:
                errors["supply"] = (
                    "Um item de composição não pode apontar "
                    "diretamente para um insumo."
                )

        elif self.item_type == BudgetSheetItemType.SUPPLY:
            if not self.supply_id:
                errors["supply"] = (
                    "O insumo é obrigatório."
                )

            if self.service_composition_id:
                errors["service_composition"] = (
                    "Um item de insumo não pode apontar para "
                    "uma composição."
                )

        elif (
            self.service_composition_id
            or self.supply_id
        ):
            errors["item_type"] = (
                "Um item livre não pode apontar para "
                "catálogos externos."
            )

        if (
            self.item_type == BudgetSheetItemType.FREE_TEXT
            and not self.description_snapshot.strip()
        ):
            errors["description_snapshot"] = (
                "A descrição do item livre é obrigatória."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Revisões precisam copiar o snapshot financeiro literalmente. Nesse
        # fluxo, subtotal e pricing_factor já pertencem à revisão de origem e
        # não podem ser reconstruídos a partir do unit_price persistido (4 casas),
        # pois o subtotal original pode ter sido calculado com um BDI de maior
        # precisão antes do arredondamento final da linha.
        preserve_financial_snapshot = kwargs.pop(
            "preserve_financial_snapshot",
            False,
        )

        # Model instances can be created not only by DRF but also by migration,
        # revision copy and management code. Normalize numeric inputs here so a
        # string snapshot never causes arithmetic/comparison TypeError.
        quantity = Decimal(str(self.quantity or 0))
        unit_price = Decimal(str(self.unit_price or 0)).quantize(
            Decimal("0.0001"),
            rounding=ROUND_HALF_UP,
        )
        unit_cost = Decimal(str(self.unit_cost or 0))

        self.quantity = quantity
        self.unit_price = unit_price
        self.unit_cost = unit_cost

        if not preserve_financial_snapshot:
            # unit_price é um snapshot de exibição/persistência com 4 casas.
            # O recálculo oficial da planilha usa custo x fator BDI com precisão
            # completa e só arredonda o subtotal da linha para centavos.
            self.subtotal = (quantity * unit_price).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            if unit_cost > 0:
                self.pricing_factor = (
                    unit_price / unit_cost
                ).quantize(
                    Decimal("0.0001"),
                    rounding=ROUND_HALF_UP,
                )
            else:
                self.pricing_factor = Decimal("0")

        self.full_clean()

        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return (
            f"{self.budget_sheet_stage} - "
            f"{self.order}. {self.description_snapshot}"
        )

class ServiceCompositionGroup(models.Model):
    code = models.CharField(max_length=80, db_index=True)
    name = models.CharField(max_length=255)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT,
        related_name="children",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "budgeting_service_composition_group"
        ordering = ("code", "name", "id")
        constraints = [
            models.UniqueConstraint(fields=("parent", "code"),
                                    condition=Q(parent__isnull=False),
                                    name="uq_comp_group_child_code"),
            models.UniqueConstraint(fields=("code",),
                                    condition=Q(parent__isnull=True),
                                    name="uq_comp_group_root_code"),
        ]

    def clean(self):
        super().clean()
        if self.parent_id is None:
            return
        ancestor_id = self.parent_id
        visited = {self.pk} if self.pk else set()
        while ancestor_id is not None:
            if ancestor_id in visited:
                raise ValidationError({"parent": "A hierarquia não pode conter ciclos."})
            visited.add(ancestor_id)
            ancestor = type(self).objects.filter(pk=ancestor_id).values("parent_id", "is_active").first()
            if ancestor is None or not ancestor["is_active"]:
                raise ValidationError({"parent": "O grupo pai deve estar ativo."})
            ancestor_id = ancestor["parent_id"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class ServiceComposition(models.Model):
    group = models.ForeignKey(
        ServiceCompositionGroup, null=True, blank=True, on_delete=models.PROTECT,
        related_name="compositions",
    )
    origin = models.CharField(
        max_length=10,
        choices=DataOrigin.choices,
        default=DataOrigin.HUB,
        db_index=True,
    )
    legacy_table = models.CharField(max_length=100, blank=True)
    legacy_id = models.BigIntegerField(null=True, blank=True)
    code = models.CharField(max_length=80, blank=True, db_index=True)
    name = models.CharField(max_length=500, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "budgeting_service_composition"
        verbose_name = "composição de serviço"
        verbose_name_plural = "composições de serviço"
        ordering = ("name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("origin", "legacy_table", "legacy_id"),
                condition=Q(legacy_id__isnull=False),
                name="uq_composition_legacy_identity",
            ),
        ]
        indexes = [
            models.Index(
                fields=("is_active", "name"),
                name="composition_active_name_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def latest_version(self) -> "ServiceCompositionVersion | None":
        prefetched_versions = getattr(
            self,
            "_prefetched_latest_versions",
            None,
        )
        if prefetched_versions is not None:
            return prefetched_versions[0] if prefetched_versions else None

        return self.versions.order_by("-number").first()


class ServiceCompositionVersion(models.Model):
    composition = models.ForeignKey(
        ServiceComposition,
        on_delete=models.PROTECT,
        related_name="versions",
    )
    number = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20,
        choices=CompositionStatus.choices,
        default=CompositionStatus.DRAFT,
        db_index=True,
    )
    origin = models.CharField(
        max_length=10,
        choices=DataOrigin.choices,
        default=DataOrigin.HUB,
    )
    unit = models.CharField(max_length=30, blank=True)
    material_total = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
    )
    labor_total = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
    )
    equipment_total = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
    )
    total = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
    )
    legacy_payload = models.JSONField(default=dict, blank=True)
    legacy_payload_hash = models.CharField(max_length=64, blank=True)
    imported_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "budgeting_service_composition_version"
        verbose_name = "versão da composição de serviço"
        verbose_name_plural = "versões das composições de serviço"
        ordering = ("composition_id", "-number")
        constraints = [
            models.UniqueConstraint(
                fields=("composition", "number"),
                name="uq_composition_version_number",
            ),
        ]

    @property
    def is_mutable(self) -> bool:
        return self.origin == DataOrigin.HUB and self.status == CompositionStatus.DRAFT

    def __str__(self) -> str:
        return f"{self.composition} - v{self.number}"


class ServiceCompositionItem(models.Model):
    # Identidade do registro no Access. Esses campos tornam a carga legada
    # idempotente e permitem atualizar o item sem duplicá-lo.
    legacy_table = models.CharField(max_length=120, blank=True, default="")
    legacy_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    version = models.ForeignKey(
        ServiceCompositionVersion,
        on_delete=models.CASCADE,
        related_name="items",
    )
    item_type = models.CharField(
        max_length=20,
        choices=CompositionItemType.choices,
        default=CompositionItemType.SUPPLY,
    )
    supply = models.ForeignKey(
        Supply,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="composition_items",
    )
    subcomposition = models.ForeignKey(
        ServiceComposition,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="parent_items",
    )
    description_snapshot = models.CharField(max_length=500)
    unit_snapshot = models.CharField(max_length=30, blank=True)
    coefficient = models.DecimalField(max_digits=18, decimal_places=6)
    material_unit_price = models.DecimalField(
        max_digits=22,
        decimal_places=8,
        default=Decimal("0"),
    )
    labor_unit_price = models.DecimalField(
        max_digits=22,
        decimal_places=8,
        default=Decimal("0"),
    )
    equipment_unit_price = models.DecimalField(
        max_digits=22,
        decimal_places=8,
        default=Decimal("0"),
    )
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "budgeting_service_composition_item"
        verbose_name = "item da composição de serviço"
        verbose_name_plural = "itens das composições de serviço"
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("legacy_table", "legacy_id"),
                condition=Q(legacy_id__isnull=False),
                name="uq_composition_item_legacy_source",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        item_type=CompositionItemType.SUPPLY,
                        supply__isnull=False,
                        subcomposition__isnull=True,
                    )
                    | Q(
                        item_type=CompositionItemType.SUBCOMPOSITION,
                        supply__isnull=True,
                        subcomposition__isnull=False,
                    )
                    | Q(
                        item_type=CompositionItemType.FREE_TEXT,
                        supply__isnull=True,
                        subcomposition__isnull=True,
                    )
                ),
                name="ck_composition_item_reference",
            ),
            models.CheckConstraint(
                condition=Q(coefficient__gte=0),
                name="ck_composition_item_coefficient_gte_0",
            ),
            models.CheckConstraint(
                condition=(
                    Q(material_unit_price__gte=0)
                    & Q(labor_unit_price__gte=0)
                    & Q(equipment_unit_price__gte=0)
                ),
                name="ck_composition_item_prices_gte_0",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.version_id and not self.version.is_mutable:
            raise ValidationError(
                "Somente versões HUB em rascunho podem ter itens alterados."
            )
        if self.item_type == CompositionItemType.SUPPLY:
            if not self.supply_id:
                raise ValidationError(
                    {"supply": "O insumo é obrigatório para este tipo de item."}
                )
            if self.subcomposition_id:
                raise ValidationError(
                    {"subcomposition": "Um item de insumo não pode ter subcomposição."}
                )
        elif self.item_type == CompositionItemType.SUBCOMPOSITION:
            if not self.subcomposition_id:
                raise ValidationError(
                    {
                        "subcomposition": (
                            "A subcomposição é obrigatória para este tipo de item."
                        )
                    }
                )
            if self.supply_id:
                raise ValidationError(
                    {"supply": "Um item de subcomposição não pode ter insumo."}
                )
        elif self.item_type == CompositionItemType.FREE_TEXT:
            if self.supply_id or self.subcomposition_id:
                raise ValidationError(
                    "Um item livre não pode apontar para insumo ou subcomposição."
                )
        if self.version_id and self.subcomposition_id == self.version.composition_id:
            raise ValidationError("Uma composição não pode conter a si própria.")

    @property
    def subtotal(self) -> Decimal:
        # O Excel calcula o custo total da linha com a precisão interna dos
        # componentes e só arredonda o resultado monetário final. Arredondar
        # material/mão de obra/equipamento separadamente altera o total ao
        # salvar e recarregar a composição.
        unit_total = (
            self.material_unit_price
            + self.labor_unit_price
            + self.equipment_unit_price
        )
        return (self.coefficient * unit_total).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )


class LegacyImportRun(models.Model):
    resource = models.CharField(
        max_length=30,
        choices=ImportResource.choices,
        default=ImportResource.LEGACY_CATALOG,
    )
    initial = models.BooleanField(default=True)
    status = models.CharField(
        max_length=20,
        choices=ImportStatus.choices,
        default=ImportStatus.RUNNING,
        db_index=True,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    counters = models.JSONField(default=dict, blank=True)
    errors = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "budgeting_legacy_import_run"
        verbose_name = "execução de importação legada"
        verbose_name_plural = "execuções de importação legada"
        ordering = ("-started_at",)
