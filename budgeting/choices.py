from django.db import models


class DataOrigin(models.TextChoices):
    LEGACY = "LEGACY", "SGO legado"
    HUB = "HUB", "Daruix Hub"

class BudgetStageLegacySource(models.TextChoices):
    WORK_COST_CENTER = (
        "WORK_COST_CENTER",
        "Centro de custo de obra",
    )
    ADMINISTRATIVE_COST_CENTER = (
        "ADMINISTRATIVE_COST_CENTER",
        "Centro de custo administrativo",
    )

class BudgetSheetStatus(models.TextChoices):
    DRAFT = "DRAFT", "Rascunho"
    FINALIZED = "FINALIZED", "Finalizada"
    CANCELLED = "CANCELLED", "Cancelada"

class BudgetSheetItemType(models.TextChoices):
    SERVICE_COMPOSITION = (
        "SERVICE_COMPOSITION",
        "Composição de serviço",
    )
    SUPPLY = "SUPPLY", "Insumo"
    FREE_TEXT = "FREE_TEXT", "Item livre"


class SupplyType(models.TextChoices):
    MATERIAL = "MATERIAL", "Material/Insumo"
    SERVICE = "SERVICE", "Serviço"
    LABOR = "LABOR", "Mão de obra"
    EQUIPMENT = "EQUIPMENT", "Equipamento"
    OTHER = "OTHER", "Não classificado"


class CompositionStatus(models.TextChoices):
    DRAFT = "DRAFT", "Rascunho"
    PUBLISHED = "PUBLISHED", "Publicada"
    HISTORICAL = "HISTORICAL", "Histórica"
    ARCHIVED = "ARCHIVED", "Arquivada"


class CompositionItemType(models.TextChoices):
    SUPPLY = "SUPPLY", "Insumo"
    SUBCOMPOSITION = "SUBCOMPOSITION", "Subcomposição"
    FREE_TEXT = "FREE_TEXT", "Item livre"


class ImportResource(models.TextChoices):
    LEGACY_CATALOG = "LEGACY_CATALOG", "Catálogo legado"


class ImportStatus(models.TextChoices):
    RUNNING = "RUNNING", "Executando"
    COMPLETED = "COMPLETED", "Concluída"
    FAILED = "FAILED", "Falha"
