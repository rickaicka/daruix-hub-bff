from functools import wraps
from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import F, Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from budgeting.models import BudgetSheet, BudgetSheetStageItem, BudgetSheetStage
from material_requisitions.models import MaterialRequisitionRevision as Revision
from material_requisitions.pagination import MaterialRequisitionPagination
from material_requisitions import serializers as sz
from material_requisitions.services import requisitions as svc


class HubEmployee(BasePermission):
    message = 'Este módulo é reservado aos colaboradores do Hub.'
    def has_permission(self, request, view):
        user = request.user
        return user.is_authenticated and user.is_active and (user.is_superuser or user.user_type == 'COLABORADOR')


def domain_errors(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ObjectDoesNotExist:
            raise NotFound('Recurso não encontrado no contexto informado.')
        except IntegrityError:
            raise svc.Conflict('Operação concorrente ou identidade duplicada. Recarregue a RM.')
        except DjangoValidationError as error:
            raise ValidationError(error.message_dict if hasattr(error, 'message_dict') else error.messages)
    return wrapped


@extend_schema_view(
    create=extend_schema(request=sz.CreateWrite, responses={201: sz.RevisionRead}),
    partial_update=extend_schema(request=sz.HeaderPatch, responses=sz.RevisionRead),
    add_section=extend_schema(request=sz.SectionWrite, responses=sz.RevisionRead),
    delete_section=extend_schema(request=sz.VersionWrite, responses=sz.RevisionRead, methods=['DELETE']),
    add_item=extend_schema(request=sz.ItemWrite, responses=sz.RevisionRead),
    item=extend_schema(request=sz.ItemFields, responses=sz.RevisionRead, methods=['PATCH']),
    load_composition=extend_schema(request=sz.LoadCompositionWrite, responses=sz.RevisionRead),
    reorder_sections=extend_schema(request=sz.ReorderWrite, responses=sz.RevisionRead),
    reorder_items=extend_schema(request=sz.ReorderWrite, responses=sz.RevisionRead),
    submit=extend_schema(request=sz.DecisionWrite, responses=sz.RevisionRead),
    approve=extend_schema(request=sz.DecisionWrite, responses=sz.RevisionRead),
    reject=extend_schema(request=sz.DecisionWrite, responses=sz.RevisionRead),
    cancel=extend_schema(request=sz.DecisionWrite, responses=sz.RevisionRead),
    generate_revision=extend_schema(request=sz.DecisionWrite, responses={201: sz.RevisionRead}),
    audit=extend_schema(responses=sz.EventRead(many=True)),
)
class MaterialRequisitionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    lookup_value_regex = r'[0-9]+'
    permission_classes = [IsAuthenticated, HubEmployee]
    serializer_class = sz.RevisionRead
    pagination_class = MaterialRequisitionPagination
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        query = Revision.objects.select_related('requisition', 'owner', 'budget_sheet').prefetch_related('sections__items')
        if self.action == 'list':
            if self.request.query_params.get('include_history') != 'true':
                query = query.filter(requisition__current_revision_id=F('id'))
            if self.request.query_params.get('include_cancelled') != 'true':
                query = query.filter(requisition__cancelled_at__isnull=True)
            for field, lookup in [('proposal', 'requisition__proposal_id'), ('status', 'status'),
                                   ('request_type', 'request_type'), ('owner', 'owner_id')]:
                if field in self.request.query_params:
                    try:
                        value = int(self.request.query_params[field])
                    except ValueError:
                        raise ValidationError({field: 'Informe um número inteiro.'})
                    query = query.filter(**{lookup: value})
            search = self.request.query_params.get('search', '').strip()
            if search:
                query = query.filter(Q(requisition__number__icontains=search) |
                    Q(requisition__proposal__code__icontains=search))
        return query.order_by('-created_at', '-id')

    def _read(self, rev, status=200):
        fresh = self.get_queryset().get(pk=rev.pk)
        return Response(sz.RevisionRead(fresh, context={'request': self.request}).data, status=status)

    def _data(self, serializer):
        value = serializer(data=self.request.data)
        value.is_valid(raise_exception=True)
        data = dict(value.validated_data)
        version = data.pop('expected_version', None)
        return version, data

    @domain_errors
    def create(self, request):
        _, data = self._data(sz.CreateWrite)
        return self._read(svc.create(request.user, data), status=201)

    @domain_errors
    def partial_update(self, request, pk=None):
        version, data = self._data(sz.HeaderPatch)
        return self._read(svc.update_header(pk, version, request.user, data))

    @action(detail=True, methods=['post'], url_path='sections')
    @domain_errors
    def add_section(self, request, pk=None):
        version, data = self._data(sz.SectionWrite)
        return self._read(svc.add_section(pk, version, request.user, **data))

    @extend_schema(request=sz.SectionPatch, responses=sz.RevisionRead, methods=['PATCH'])
    @action(detail=True, methods=['delete', 'patch'], url_path=r'sections/(?P<section_id>[0-9]+)')
    @domain_errors
    def delete_section(self, request, pk=None, section_id=None):
        if request.method == 'PATCH':
            version, data = self._data(sz.SectionPatch)
            return self._read(svc.update_section(pk, version, request.user, section_id, data['description']))
        version, _ = self._data(sz.VersionWrite)
        return self._read(svc.remove_section(pk, version, request.user, section_id))

    @extend_schema(responses=sz.SectionSupplyRead(many=True))
    @action(detail=True, methods=['get'], url_path=r'sections/(?P<section_id>[0-9]+)/supplies')
    @domain_errors
    def section_supplies(self, request, pk=None, section_id=None):
        rev = self.get_object()
        section = rev.sections.select_related('source_stage').get(pk=section_id)
        options = svc.section_supply_options(section, rev, request.query_params.get('search', ''))
        page = self.paginate_queryset(options)
        return self.get_paginated_response(page)

    @action(detail=True, methods=['post'], url_path=r'sections/(?P<section_id>[0-9]+)/items')
    @domain_errors
    def add_item(self, request, pk=None, section_id=None):
        version, data = self._data(sz.ItemWrite)
        return self._read(svc.add_item(pk, version, request.user, section_id, data))

    @action(detail=True, methods=['patch', 'delete'], url_path=r'items/(?P<item_id>[0-9]+)')
    @domain_errors
    def item(self, request, pk=None, item_id=None):
        serializer = sz.VersionWrite if request.method == 'DELETE' else sz.ItemFields
        version, data = self._data(serializer)
        return self._read(svc.change_item(pk, version, request.user, item_id,
                          data if request.method == 'PATCH' else None))

    @action(detail=True, methods=['post'], url_path=r'sections/(?P<section_id>[0-9]+)/load-composition')
    @domain_errors
    def load_composition(self, request, pk=None, section_id=None):
        version, data = self._data(sz.LoadCompositionWrite)
        rev, report = svc.load_composition(pk, version, request.user, section_id, **data)
        response = self._read(rev)
        response.data['composition_load_report'] = report
        return response

    @action(detail=True, methods=['get'])
    def diff(self, request, pk=None):
        rev = self.get_object()
        if not rev.previous_id:
            return Response({'previous': None, 'current': rev.pk, 'header_changes': {},
                             'added': [], 'removed': [], 'changed': [], 'section_changes': []})
        previous = rev.previous
        fields = ['request_type', 'reference_date', 'delivery_date', 'notes', 'is_rental']
        header = {key: {'before': str(getattr(previous, key)), 'after': str(getattr(rev, key))}
                  for key in fields if getattr(previous, key) != getattr(rev, key)}
        def contents(value):
            result = {}
            for section in value.sections.all():
                for item in section.items.all():
                    key = str(item.lineage)
                    result[key] = {'section_source': section.source_composition_id,
                        'position': item.position, 'supply': item.supply_id, 'description': item.description,
                        'unit': item.unit, 'quantity': str(item.quantity), 'period': item.period,
                        'period_unit': item.period_unit, 'notes': item.notes, 'source_path': item.source_path}
            return result
        def section_contents(value):
            return {section.position: {'position': section.position, 'stage': section.source_stage_id,
                'stage_name': section.stage_name, 'description': section.description}
                for section in value.sections.all()}
        old_sections, new_sections = section_contents(previous), section_contents(rev)
        section_changes = [{'before': old_sections.get(key), 'after': new_sections.get(key)}
            for key in sorted(old_sections.keys() | new_sections.keys())
            if old_sections.get(key) != new_sections.get(key)]
        old, new = contents(previous), contents(rev)
        return Response({'previous': previous.pk, 'current': rev.pk, 'header_changes': header,
            'section_changes': section_changes,
            'added': [new[k] for k in new.keys() - old.keys()],
            'removed': [old[k] for k in old.keys() - new.keys()],
            'changed': [{'before': old[k], 'after': new[k]} for k in old.keys() & new.keys() if old[k] != new[k]]})

    @action(detail=True, methods=['post'], url_path='reorder-sections')
    @domain_errors
    def reorder_sections(self, request, pk=None):
        version, data = self._data(sz.ReorderWrite)
        return self._read(svc.reorder(pk, version, request.user, data['order']))

    @action(detail=True, methods=['post'], url_path=r'sections/(?P<section_id>[0-9]+)/reorder-items')
    @domain_errors
    def reorder_items(self, request, pk=None, section_id=None):
        version, data = self._data(sz.ReorderWrite)
        return self._read(svc.reorder(pk, version, request.user, data['order'], section_id))

    def _decision(self, name, pk):
        version, data = self._data(sz.DecisionWrite)
        rev = svc.decide(pk, version, self.request.user, name, data.get('reason', ''))
        from material_requisitions.services.notifications import after_decision
        after_decision(rev, self.request.user, name)
        return self._read(rev)

    @action(detail=True, methods=['post'])
    @domain_errors
    def submit(self, request, pk=None): return self._decision('submit', pk)

    @action(detail=True, methods=['post'])
    @domain_errors
    def approve(self, request, pk=None): return self._decision('approve', pk)

    @action(detail=True, methods=['post'])
    @domain_errors
    def reject(self, request, pk=None): return self._decision('reject', pk)

    @action(detail=True, methods=['post'])
    @domain_errors
    def cancel(self, request, pk=None): return self._decision('cancel', pk)

    @action(detail=True, methods=['post'], url_path='generate-revision')
    @domain_errors
    def generate_revision(self, request, pk=None):
        version, data = self._data(sz.DecisionWrite)
        raise ValidationError('Requisições de materiais não possuem revisão. Consulte o histórico de operações.')

    @action(detail=True, methods=['get'])
    def revisions(self, request, pk=None):
        rev = self.get_object()
        page = self.paginate_queryset(self.get_queryset().filter(requisition=rev.requisition))
        return self.get_paginated_response(sz.RevisionRead(page, many=True, context={'request': request}).data)

    @action(detail=True, methods=['get'])
    def audit(self, request, pk=None):
        rev = self.get_object()
        query = rev.events.all()
        page = self.paginate_queryset(query)
        return self.get_paginated_response(sz.EventRead(page, many=True).data)

    @action(detail=False, methods=['get'])
    @domain_errors
    def context(self, request):
        def number(name):
            try: return int(request.query_params[name])
            except (KeyError, ValueError): raise ValidationError({name: 'Informe um ID inteiro.'})
        if 'budget_sheet' not in request.query_params:
            proposal = number('proposal')
            # Mantém o envelope paginado do contexto, agora com no máximo uma origem.
            sheet = svc.latest_finalized_sheet(proposal)
            values = [] if sheet is None else [sheet]
            page = self.paginate_queryset(values)
            return self.get_paginated_response([{'id': s.pk, 'number': s.number,
                'revision': s.revision, 'proposal': s.proposal_id} for s in page])
        sheet = BudgetSheet.objects.get(pk=number('budget_sheet'))
        svc._eligible_sheet(sheet)
        if 'proposal' in request.query_params and sheet.proposal_id != number('proposal'):
            raise ValidationError('A PO não pertence ao PC informado.')
        if 'stage' not in request.query_params:
            page = self.paginate_queryset(sheet.stages.order_by('order', 'id'))
            return self.get_paginated_response([{'id': s.pk, 'name': s.name_snapshot,
                                                  'order': s.order} for s in page])
        stage = BudgetSheetStage.objects.get(pk=number('stage'), budget_sheet=sheet)
        query = stage.items.filter(item_type='SERVICE_COMPOSITION')
        term = request.query_params.get('search', '').strip()
        if term: query = query.filter(description_snapshot__icontains=term)
        page = self.paginate_queryset(query.order_by('order', 'id'))
        return self.get_paginated_response([{'id': i.pk, 'description': i.description_snapshot,
            'unit': i.unit_snapshot, 'composition': i.service_composition_id,
            'snapshot': i.composition_snapshot, 'quantity': str(i.quantity)} for i in page])
