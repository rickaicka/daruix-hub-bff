"""Domínio operacional de RM, independente do espelho importado do Access."""
import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class RMStatus(models.IntegerChoices):
    REJECTED = 0, 'Reprovada'
    APPROVED = 1, 'Aprovada'
    CANCELLED = 2, 'Cancelada'
    DRAFT = 3, 'Rascunho'
    PENDING = 4, 'Aguardando aprovação'


class RMType(models.IntegerChoices):
    MATERIAL = 0, 'Material'
    SERVICE = 1, 'Serviço'
    MIXED = 2, 'Material e Serviço'


class MaterialRequisition(models.Model):
    proposal = models.ForeignKey('commercial.Proposal', on_delete=models.PROTECT)
    sequence = models.PositiveIntegerField()
    number = models.CharField(max_length=100, unique=True)
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    creation_key = models.UUIDField(unique=True)
    creation_hash = models.CharField(max_length=64)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    current_revision = models.ForeignKey('MaterialRequisitionRevision', on_delete=models.PROTECT,
                                         null=True, blank=True, related_name='+')
    approved_revision = models.ForeignKey('MaterialRequisitionRevision', on_delete=models.PROTECT,
                                          null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'budgeting_materialrequisition'
        constraints = [models.UniqueConstraint(fields=['proposal', 'sequence'], name='uq_rm_pc_sequence')]


class MaterialRequisitionRevision(models.Model):
    requisition = models.ForeignKey(MaterialRequisition, on_delete=models.PROTECT, related_name='revisions')
    number = models.PositiveIntegerField(default=0)
    previous = models.OneToOneField('self', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    budget_sheet = models.ForeignKey('budgeting.BudgetSheet', on_delete=models.PROTECT)
    source_snapshot = models.JSONField(default=dict)
    status = models.PositiveSmallIntegerField(choices=RMStatus.choices, default=RMStatus.DRAFT)
    request_type = models.PositiveSmallIntegerField(choices=RMType.choices, default=RMType.MATERIAL)
    reference_date = models.DateField(default=timezone.localdate)
    delivery_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    reason = models.TextField(blank=True)
    is_rental = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'budgeting_materialrequisitionrevision'
        constraints = [
            models.UniqueConstraint(fields=['requisition', 'number'], name='uq_rm_revision'),
            models.CheckConstraint(condition=Q(status__in=[0, 1, 2, 3, 4]), name='ck_rm_status'),
            models.CheckConstraint(condition=Q(request_type__in=[0, 1, 2]), name='ck_rm_type'),
        ]
        ordering = ['requisition_id', '-number']


class MaterialRequisitionSection(models.Model):
    revision = models.ForeignKey(MaterialRequisitionRevision, on_delete=models.PROTECT, related_name='sections')
    source_stage = models.ForeignKey('budgeting.BudgetSheetStage', on_delete=models.PROTECT)
    source_composition = models.ForeignKey('budgeting.BudgetSheetStageItem', on_delete=models.PROTECT, null=True, blank=True)
    stage_name = models.CharField(max_length=255)
    description = models.CharField(max_length=500)
    unit = models.CharField(max_length=30, blank=True)
    composition_snapshot = models.JSONField(default=dict)
    position = models.PositiveIntegerField()

    class Meta:
        db_table = 'budgeting_materialrequisitionsection'
        ordering = ['position', 'id']
        constraints = [models.UniqueConstraint(fields=['revision', 'source_stage', 'source_composition'],
                                               name='uq_rm_section_context')]


class MaterialRequisitionItem(models.Model):
    lineage = models.UUIDField(default=uuid.uuid4, editable=False)
    section = models.ForeignKey(MaterialRequisitionSection, on_delete=models.PROTECT, related_name='items')
    supply = models.ForeignKey('budgeting.Supply', on_delete=models.PROTECT)
    description = models.CharField(max_length=500)
    unit = models.CharField(max_length=30)
    supply_type = models.CharField(max_length=20)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    period = models.PositiveIntegerField(null=True, blank=True)
    period_unit = models.CharField(max_length=10, blank=True,
        choices=[('HOUR', 'Hora'), ('DAY', 'Dia'), ('WEEK', 'Semana'), ('MONTH', 'Mês')])
    notes = models.TextField(blank=True)
    source_path = models.CharField(max_length=255, blank=True)
    position = models.PositiveIntegerField()

    class Meta:
        db_table = 'budgeting_materialrequisitionitem'
        ordering = ['position', 'id']
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name='ck_rm_item_quantity')]


class MaterialRequisitionEvent(models.Model):
    revision = models.ForeignKey(MaterialRequisitionRevision, on_delete=models.PROTECT, related_name='events')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=40)
    version = models.PositiveIntegerField()
    reason = models.TextField(blank=True)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'budgeting_materialrequisitionevent'
        ordering = ['id']


class LegacyMaterialRequest(models.Model):
    """Espelho de leitura do legado; não é uma RM operacional do Hub."""
    legacy_id = models.BigIntegerField(unique=True)
    pc = models.CharField(max_length=255, blank=True, db_index=True)
    legacy_number = models.BigIntegerField(null=True, blank=True)
    legacy_type = models.IntegerField(null=True, blank=True)
    legacy_status = models.CharField(max_length=255, blank=True)
    raw_payload = models.JSONField()
    payload_hash = models.CharField(max_length=64)
    imported_at = models.DateTimeField()

    class Meta:
        db_table = 'budgeting_legacy_material_request'


class LegacyMaterialRequestItem(models.Model):
    request = models.ForeignKey(LegacyMaterialRequest, on_delete=models.PROTECT,
                                related_name='legacy_items')
    legacy_item_id = models.BigIntegerField()
    raw_payload = models.JSONField()
    payload_hash = models.CharField(max_length=64)
    imported_at = models.DateTimeField()

    class Meta:
        db_table = 'budgeting_legacy_material_request_item'
        constraints = [models.UniqueConstraint(fields=['request', 'legacy_item_id'],
                                                name='uq_legacy_rm_item')]


class LegacyMaterialRequestIssue(models.Model):
    """Ocorrências preservadas por identidade técnica, inclusive duplicados exatos."""
    identity = models.CharField(max_length=64, unique=True)
    reason = models.CharField(max_length=50, db_index=True)
    raw_payload = models.JSONField()
    imported_at = models.DateTimeField()

    class Meta:
        db_table = 'budgeting_legacy_material_request_issue'

