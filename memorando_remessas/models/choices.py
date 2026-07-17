from django.db import models


class ShipmentMemoStatus(models.TextChoices):
    DRAFT = "RASCUNHO", "Rascunho"
    PROCESSING = "PROCESSANDO_ENVIO", "Processando envio"
    SENT = "ENVIADO", "Enviado"
    FAILED = "FALHA_ENVIO", "Falha no envio"
    CANCELLED = "CANCELADO", "Cancelado"


class WorkSource(models.TextChoices):
    ACCESS = "ACCESS", "Access"
    HUB = "HUB", "Daruix Hub"


class ShipmentMemoOptionType(models.TextChoices):
    SPECIES = "ESPECIE", "Espécie"
    PURPOSE = "FINALIDADE", "Finalidade"
    REQUEST = "SOLICITACAO", "Solicitação"


class ShipmentMemoHistoryAction(models.TextChoices):
    CREATED = "CRIADO", "Criado"
    UPDATED = "ALTERADO", "Alterado"
    SENT = "ENVIADO", "Enviado"
    CANCELLED = "CANCELADO", "Cancelado"
    REVISION_CREATED = "REVISAO_CRIADA", "Revisão criada"
    FILE_ADDED = "ARQUIVO_ADICIONADO", "Arquivo adicionado"
    FILE_REMOVED = "ARQUIVO_REMOVIDO", "Arquivo removido"