from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from .choices import (
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
    code = models.CharField(max_length=80, blank=True, db_index=True)
    description = models.CharField(max_length=500, db_index=True)
    supply_type = models.CharField(
        max_length=20,
        choices=SupplyType.choices,
        default=SupplyType.OTHER,
    )
    unit = models.CharField(max_length=30, blank=True)
    specification = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    legacy_payload = models.JSONField(default=dict, blank=True)
    legacy_payload_hash = models.CharField(max_length=64, blank=True)
    imported_at = models.DateTimeField(null=True, blank=True)
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

    def __str__(self) -> str:
        return self.description


class ServiceComposition(models.Model):
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

    def __str__(self) -> str:
        return self.name

    @property
    def latest_version(self):
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
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
    )
    labor_unit_price = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
    )
    equipment_unit_price = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
    )
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "budgeting_service_composition_item"
        verbose_name = "item da composição de serviço"
        verbose_name_plural = "itens das composições de serviço"
        ordering = ("position", "id")

    def clean(self) -> None:
        super().clean()
        if self.version_id and not self.version.is_mutable:
            raise ValidationError("Somente versões HUB em rascunho podem ter itens alterados.")
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
        unit_total = (
            self.material_unit_price
            + self.labor_unit_price
            + self.equipment_unit_price
        )
        return self.coefficient * unit_total


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
