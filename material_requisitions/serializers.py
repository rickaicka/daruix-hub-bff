from collections.abc import Mapping
from decimal import Decimal
from rest_framework import serializers
from material_requisitions.models import (MaterialRequisitionRevision as Revision,
    MaterialRequisitionSection as Section, MaterialRequisitionItem as Item,
    MaterialRequisitionEvent as Event, RMStatus as Status)
from material_requisitions.services.requisitions import privileged, can_decide_rm


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            raise serializers.ValidationError({'non_field_errors': ['Envie um objeto JSON.']})
        extra = set(data) - set(self.fields)
        if extra:
            raise serializers.ValidationError({k: 'Campo não permitido.' for k in extra})
        return super().to_internal_value(data)


class HeaderWrite(StrictSerializer):
    reference_date = serializers.DateField(required=False)
    delivery_date = serializers.DateField(required=False, allow_null=True)
    request_type = serializers.ChoiceField(choices=[0, 1, 2], required=False)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=10000)
    is_rental = serializers.BooleanField(required=False)


class CreateWrite(HeaderWrite):
    creation_key = serializers.UUIDField()
    proposal = serializers.IntegerField(min_value=1, required=False)
    expected_budget_sheet = serializers.IntegerField(min_value=1, required=False)
    # Compatibilidade transitória: é conferência da origem automática, nunca uma escolha.
    budget_sheet = serializers.IntegerField(min_value=1, required=False)

    def validate(self, data):
        if 'proposal' not in data and 'budget_sheet' not in data:
            raise serializers.ValidationError({'proposal': 'Informe o PC da RM.'})
        return data
    reference_date = serializers.DateField()


class HeaderPatch(HeaderWrite):
    expected_version = serializers.IntegerField(min_value=1)


class VersionWrite(StrictSerializer):
    expected_version = serializers.IntegerField(min_value=1)


class DecisionWrite(VersionWrite):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=10000)


class SectionWrite(VersionWrite):
    source_stage = serializers.IntegerField(min_value=1)
    description = serializers.CharField(max_length=500, trim_whitespace=True)


class SectionPatch(VersionWrite):
    description = serializers.CharField(max_length=500, trim_whitespace=True)


class ItemFields(StrictSerializer):
    quantity = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal('0.000001'), required=False)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=10000)
    period = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    period_unit = serializers.ChoiceField(choices=['', 'HOUR', 'DAY', 'WEEK', 'MONTH'], required=False)
    expected_version = serializers.IntegerField(min_value=1)


class ItemWrite(ItemFields):
    supply = serializers.IntegerField(min_value=1)
    source_path = serializers.CharField(required=False, allow_blank=True, max_length=255)
    quantity = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal('0.000001'))


class ItemRead(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = ['id', 'lineage', 'supply', 'description', 'unit', 'supply_type', 'quantity', 'period',
                  'period_unit', 'notes', 'source_path', 'position']


class SectionRead(serializers.ModelSerializer):
    items = ItemRead(many=True, read_only=True)
    class Meta:
        model = Section
        fields = ['id', 'source_stage', 'source_composition', 'stage_name', 'description',
                  'unit', 'position', 'composition_snapshot', 'items']


class RevisionRead(serializers.ModelSerializer):
    number = serializers.CharField(source='requisition.number')
    revision = serializers.IntegerField(source='number')
    proposal = serializers.IntegerField(source='requisition.proposal_id')
    requester = serializers.IntegerField(source='requisition.requester_id')
    cancelled_at = serializers.DateTimeField(source='requisition.cancelled_at')
    current_revision = serializers.IntegerField(source='requisition.current_revision_id')
    approved_revision = serializers.IntegerField(source='requisition.approved_revision_id', allow_null=True)
    sections = SectionRead(many=True, read_only=True)
    allowed_actions = serializers.SerializerMethodField()
    effective_status = serializers.SerializerMethodField()
    is_approved_effective = serializers.SerializerMethodField()

    def get_effective_status(self, rev) -> int:
        return Status.CANCELLED if rev.requisition.cancelled_at else rev.status

    def get_is_approved_effective(self, rev) -> bool:
        return not rev.requisition.cancelled_at and rev.requisition.approved_revision_id == rev.pk

    def get_allowed_actions(self, rev) -> dict[str, bool]:
        user = self.context['request'].user
        root = rev.requisition
        current = root.current_revision_id == rev.pk and not root.cancelled_at
        manager = privileged(user)
        approver = can_decide_rm(rev, user)
        editable = current and rev.owner_id == user.pk and rev.status in (Status.DRAFT, Status.PENDING)
        return {'edit': editable, 'submit': editable and rev.status == Status.DRAFT,
                'approve': current and approver and rev.status == Status.PENDING,
                'reject': current and approver and rev.status == Status.PENDING,
                'generate_revision': False,
                'cancel': current and (manager or editable)}

    class Meta:
        model = Revision
        fields = ['id', 'requisition', 'number', 'revision', 'previous', 'proposal', 'requester',
                  'owner', 'budget_sheet', 'source_snapshot', 'status', 'request_type',
                  'reference_date', 'delivery_date', 'notes', 'is_rental', 'reason', 'version',
                  'current_revision', 'approved_revision', 'cancelled_at', 'sections', 'allowed_actions',
                  'effective_status', 'is_approved_effective']


class EventRead(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = ['id', 'revision', 'actor', 'action', 'version', 'reason', 'payload', 'created_at']


class LoadCompositionWrite(VersionWrite):
    recalculate = serializers.BooleanField(default=False)
    multiplier = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal('0.000001'))
    period = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    period_unit = serializers.ChoiceField(choices=['', 'HOUR', 'DAY', 'WEEK', 'MONTH'], required=False)


class ReorderWrite(VersionWrite):
    order = serializers.ListField(child=serializers.IntegerField(min_value=1))


class SectionSupplyRead(serializers.Serializer):
    id = serializers.IntegerField()
    description = serializers.CharField()
    unit = serializers.CharField()
    supply_type = serializers.CharField()
    source_path = serializers.CharField()
