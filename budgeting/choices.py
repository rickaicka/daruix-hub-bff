from django.db import models


class DataOrigin(models.TextChoices):
    LEGACY = "LEGACY", "SGO legado"
    HUB = "HUB", "Daruix Hub"


class SupplyType(models.TextChoices):
    MATERIAL = "MATERIAL", "Material"
    LABOR = "LABOR", "Mão de obra"
    EQUIPMENT = "EQUIPMENT", "Equipamento"
    OTHER = "OTHER", "Outro"


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

