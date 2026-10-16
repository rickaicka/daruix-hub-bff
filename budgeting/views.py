from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Case, F, IntegerField, Max, Q, Value, When
from django.http import HttpResponse
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
)
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .api_utils import raise_api_validation_error
from .choices import BudgetSheetStatus, DataOrigin, SupplyType
from .models import (
    BudgetSheet,
    BudgetSheetStage,
    BudgetSheetStageItem,
    BudgetStageCatalog,
    MaterialGroup,
    ServiceCompositionGroup,
    UnitMeasure,
)
from .pagination import (
    BudgetSheetPagination,
    BudgetStagePagination,
    SupplyAutocompletePagination,
    SupplyPagination,
)
from .selectors import service_composition_queryset, supply_queryset
from .serializers import (
    BudgetExportPreviewSerializer,
    BudgetCompositionComponentEnabledSerializer,
    BudgetCompositionCustomizationSerializer,
    BudgetCostConfigurationReadSerializer,
    BudgetCostConfigurationWriteSerializer,
    BudgetBdiApplicationWriteSerializer,
    BudgetSheetDiffSerializer,
    BudgetSheetSerializer,
    BudgetSheetRevisionSerializer,
    BudgetSheetStageItemSerializer,
    BudgetSheetStageReadSerializer,
    BudgetSheetStageWriteSerializer,
    BudgetStageCatalogCreateSerializer,
    BudgetStageCatalogSerializer,
    CompositionVersionSerializer,
    GenerateBudgetSheetRevisionSerializer,
    GrupoMaterialSerializer,
    ItemReorderSerializer,
    ServiceCompositionReadSerializer,
    ServiceCompositionGroupSerializer,
    StageReorderSerializer,
    ServiceCompositionWriteSerializer,
    SupplyAutocompleteSerializer,
    SupplySerializer,
    SupplyTypeSerializer,
    UnidadeMedidaSerializer,
)
from .services.compositions import (
    new_version as create_new_version,
)
from .services.compositions import (
    publish as publish_composition,
)
from .services.budget_sheets import (
    build_revision_diff,
    delete_stage_item,
    ensure_budget_sheet_editable,
    finalize_budget_sheet,
    generate_budget_revision,
    recalculate_budget_totals,
    revision_group_query,
    set_budget_sheet_bdi_application,
    reorder_stage_items,
    update_composition_component_enabled,
)
from .services.budget_composition_customization import customize_budget_composition
from .services.budget_costs import (
    get_budget_cost_configuration,
    save_budget_cost_configuration,
)
from .services.budget_sheet_exports import (
    build_export_preview,
    export_budget_sheet_xlsx,
    export_budget_sheet_pdf,
    export_budget_sheet_pdfs,
)
from .filters import SupplyAutocompleteFilter


class FilteredViewSetMixin:
    filter_backends = (
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    )


class BudgetStageCatalogViewSet(
    FilteredViewSetMixin,
    mixins.CreateModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    serializer_class = BudgetStageCatalogSerializer
    pagination_class = BudgetStagePagination

    search_fields = (
        "name",
        "code",
    )
    ordering_fields = (
        "name",
        "code",
        "legacy_category",
        "created_at",
        "updated_at",
    )
    ordering = (
        "name",
        "id",
    )
    filterset_fields = (
        "origin",
        "legacy_source",
        "legacy_category",
        "is_active",
    )

    def get_serializer_class(self):
        if self.action == "create":
            return BudgetStageCatalogCreateSerializer

        return BudgetStageCatalogSerializer

    def get_queryset(self):
        return BudgetStageCatalog.objects.all()


class BudgetSheetViewSet(
    FilteredViewSetMixin,
    viewsets.ModelViewSet,
):
    serializer_class = BudgetSheetSerializer
    pagination_class = BudgetSheetPagination

    search_fields = (
        "number",
        "proposal__code",
        "party__legal_name",
        "party__trade_name",
    )
    ordering_fields = (
        "number",
        "revision",
        "reference_date",
        "status",
        "total_amount",
        "created_at",
        "updated_at",
    )
    ordering = (
        "-reference_date",
        "-id",
    )
    filterset_fields = (
        "proposal",
        "party",
        "department",
        "status",
        "reference_date",
        "revision_root",
    )

    def get_queryset(self):
        return (
            BudgetSheet.objects
            .select_related(
                "proposal",
                "party",
                "department",
                "revision_root",
                "previous_revision",
                "finalized_by",
            )
            .prefetch_related(
                "stages__stage",
                "stages__items__service_composition",
                "stages__items__supply",
            )
        )

    def perform_create(self, serializer):
        user = self.request.user
        actor = user if getattr(user, "pk", None) else None

        serializer.save(
            created_by=actor,
            updated_by=actor,
        )

    def perform_update(self, serializer):
        user = self.request.user

        try:
            with transaction.atomic():
                locked_instance = (
                    BudgetSheet.objects
                    .select_for_update()
                    .get(pk=serializer.instance.pk)
                )

                ensure_budget_sheet_editable(locked_instance)
                serializer.instance = locked_instance
                serializer.save(
                    updated_by=(
                        user if getattr(user, "pk", None) else None
                    ),
                )
        except DjangoValidationError as error:
            raise_api_validation_error(error)

    def perform_destroy(self, instance):
        try:
            with transaction.atomic():
                locked_instance = (
                    BudgetSheet.objects
                    .select_for_update()
                    .get(pk=instance.pk)
                )

                ensure_budget_sheet_editable(locked_instance)
                locked_instance.delete()
        except DjangoValidationError as error:
            raise_api_validation_error(error)

    @staticmethod
    def _ensure_editable(budget_sheet):
        try:
            ensure_budget_sheet_editable(budget_sheet)
        except DjangoValidationError as error:
            raise_api_validation_error(error)

    @extend_schema(
        methods=["GET"],
        responses=BudgetCostConfigurationReadSerializer,
    )
    @extend_schema(
        methods=["PUT"],
        request=BudgetCostConfigurationWriteSerializer,
        responses=BudgetCostConfigurationReadSerializer,
    )
    @action(
        detail=True,
        methods=["get", "put"],
        url_path="cost-configuration",
    )
    def cost_configuration(self, request, pk=None):
        budget_sheet = self.get_object()

        if request.method == "GET":
            data = get_budget_cost_configuration(budget_sheet)

            return Response(
                BudgetCostConfigurationReadSerializer(data).data
            )

        input_serializer = BudgetCostConfigurationWriteSerializer(
            data=request.data
        )
        input_serializer.is_valid(raise_exception=True)

        try:
            data = save_budget_cost_configuration(
                budget_sheet.pk,
                input_serializer.validated_data,
                user=request.user,
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)

        return Response(
            BudgetCostConfigurationReadSerializer(data).data
        )

    @extend_schema(
        request=BudgetBdiApplicationWriteSerializer,
        responses=BudgetSheetSerializer,
    )
    @action(
        detail=True,
        methods=("put",),
        url_path="bdi-application",
    )
    def bdi_application(self, request, pk=None):
        budget_sheet = self.get_object()
        input_serializer = BudgetBdiApplicationWriteSerializer(
            data=request.data
        )
        input_serializer.is_valid(raise_exception=True)

        mode = input_serializer.validated_data["mode"]

        try:
            updated = set_budget_sheet_bdi_application(
                budget_sheet.pk,
                apply_bdi=mode == "ALL",
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)

        updated.refresh_from_db()

        return Response(
            BudgetSheetSerializer(
                updated,
                context=self.get_serializer_context(),
            ).data
        )

    @extend_schema(
        responses=BudgetSheetRevisionSerializer(many=True),
    )
    @action(
        detail=True,
        methods=("get",),
        url_path="revisions",
        pagination_class=None,
    )
    def revisions(self, request, pk=None):
        budget_sheet = self.get_object()

        queryset = (
            BudgetSheet.objects
            .filter(revision_group_query(budget_sheet))
            .order_by("revision", "id")
        )

        serializer = BudgetSheetRevisionSerializer(
            queryset,
            many=True,
            context={
                **self.get_serializer_context(),
                "current_budget_sheet_id": budget_sheet.pk,
            },
        )

        return Response(serializer.data)

    @extend_schema(
        request=None,
        responses=BudgetSheetSerializer,
    )
    @action(
        detail=True,
        methods=("post",),
        url_path="finalize",
    )
    def finalize(self, request, pk=None):
        budget_sheet = self.get_object()

        try:
            finalized = finalize_budget_sheet(
                budget_sheet.pk,
                user=request.user,
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)

        serializer = self.get_serializer(finalized)

        return Response(serializer.data)

    @extend_schema(
        request=GenerateBudgetSheetRevisionSerializer,
        responses={201: BudgetSheetSerializer},
    )
    @action(
        detail=True,
        methods=("post",),
        url_path="generate-revision",
    )
    def generate_revision(self, request, pk=None):
        budget_sheet = self.get_object()

        input_serializer = GenerateBudgetSheetRevisionSerializer(
            data=request.data,
        )
        input_serializer.is_valid(raise_exception=True)

        try:
            revision = generate_budget_revision(
                budget_sheet.pk,
                reason=input_serializer.validated_data["reason"],
                user=request.user,
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)
        except IntegrityError as error:
            raise ValidationError(
                {
                    "revision": (
                        "Já existe uma nova revisão para esta planilha."
                    )
                }
            ) from error

        serializer = self.get_serializer(revision)

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        request=None,
        responses=BudgetSheetSerializer,
    )
    @action(
        detail=True,
        methods=("post",),
        url_path="recalculate",
    )
    def recalculate(self, request, pk=None):
        budget_sheet = self.get_object()

        try:
            recalculate_budget_totals(budget_sheet.pk)
        except DjangoValidationError as error:
            raise_api_validation_error(error)

        refreshed = self.get_queryset().get(pk=budget_sheet.pk)

        return Response(
            self.get_serializer(refreshed).data
        )

    @extend_schema(
        responses=BudgetSheetDiffSerializer,
    )
    @action(
        detail=True,
        methods=("get",),
        url_path="diff",
    )
    def diff(self, request, pk=None):
        return Response(
            build_revision_diff(self.get_object())
        )

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="audience",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                enum=["CLIENT", "DARUIX"],
                description=(
                    "CLIENT expõe somente etapa e item/composição. "
                    "DARUIX inclui a abertura dos componentes internos."
                ),
            )
        ],
        responses=BudgetExportPreviewSerializer,
    )
    @action(
        detail=True,
        methods=("get",),
        url_path="export-preview",
    )
    def export_preview(self, request, pk=None):
        self.get_object()  # Aplica queryset e permissões de objeto antes da exportação.
        audience = str(
            request.query_params.get("audience") or ""
        ).upper()

        try:
            data = build_export_preview(
                int(pk),
                audience,
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)

        return Response(data)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="audience",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                enum=["CLIENT", "DARUIX"],
            )
        ],
        responses={
            (
                200,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ): OpenApiTypes.BINARY
        },
    )
    @action(
        detail=True,
        methods=("get",),
        url_path="export-xlsx",
    )
    def export_xlsx(self, request, pk=None):
        self.get_object()  # Aplica queryset e permissões de objeto antes da exportação.
        audience = str(
            request.query_params.get("audience") or ""
        ).upper()

        try:
            content, filename = export_budget_sheet_xlsx(
                int(pk),
                audience,
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)

        response = HttpResponse(
            content,
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )

        response["Content-Disposition"] = (
            f'attachment; filename="{filename}"'
        )
        response["Cache-Control"] = "private, no-store"

        return response

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="audience",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                enum=["CLIENT", "DARUIX"],
            ),
            OpenApiParameter(
                name="document",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=["PLANILHA", "BDI", "DI"],
                default="PLANILHA",
                description="Relatório em A4 paisagem, com conteúdo de acordo com o público.",
            ),
        ],
        responses={
            (
                200,
                "application/pdf",
            ): OpenApiTypes.BINARY
        },
    )
    @action(
        detail=True,
        methods=("get",),
        url_path="export-pdf",
    )
    def export_pdf(self, request, pk=None):
        self.get_object()  # Aplica queryset e permissões de objeto antes da exportação.
        audience = str(
            request.query_params.get("audience") or ""
        ).upper()

        document = str(request.query_params.get("document", "PLANILHA")).strip().upper()

        try:
            content, filename = export_budget_sheet_pdf(
                int(pk),
                audience,
                document,
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)

        response = HttpResponse(
            content,
            content_type=(
                "application/pdf"
            ),
        )

        response["Content-Disposition"] = (
            f'attachment; filename="{filename}"'
        )
        response["Cache-Control"] = "private, no-store"

        return response

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="audience",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                enum=["CLIENT", "DARUIX"],
            ),
        ],
        responses={
            (
                200,
                "application/zip",
            ): OpenApiTypes.BINARY
        },
    )
    @action(
        detail=True,
        methods=("get",),
        url_path="export-pdfs",
    )
    def export_pdfs(self, request, pk=None):
        self.get_object()  # Aplica queryset e permissões de objeto antes da exportação.
        audience = str(
            request.query_params.get("audience") or ""
        ).upper()

        try:
            content, filename = export_budget_sheet_pdfs(
                int(pk),
                audience,
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)

        response = HttpResponse(
            content,
            content_type=(
                "application/zip"
            ),
        )

        response["Content-Disposition"] = (
            f'attachment; filename="{filename}"'
        )
        response["Cache-Control"] = "private, no-store"

        return response

    def _stage_serializer_context(
        self,
        budget_sheet,
    ):
        return {
            **self.get_serializer_context(),
            "budget_sheet": budget_sheet,
        }

    @extend_schema(
        methods=["GET"],
        responses=BudgetSheetStageReadSerializer(many=True),
    )
    @extend_schema(
        methods=["POST"],
        request=BudgetSheetStageWriteSerializer,
        responses={201: BudgetSheetStageReadSerializer},
    )
    @action(
        detail=True,
        methods=("get", "post"),
        url_path="stages",
    )
    def stages(self, request, pk=None):
        budget_sheet = self.get_object()

        if request.method == "GET":
            queryset = (
                budget_sheet.stages
                .select_related("stage")
                .order_by("order", "id")
            )

            serializer = BudgetSheetStageReadSerializer(
                queryset,
                many=True,
                context=self.get_serializer_context(),
            )

            return Response(serializer.data)

        with transaction.atomic():
            locked_sheet = (
                BudgetSheet.objects
                .select_for_update()
                .get(pk=budget_sheet.pk)
            )

            self._ensure_editable(locked_sheet)

            data = request.data.copy()

            if not data.get("order"):
                last_order = (
                    locked_sheet.stages
                    .aggregate(max_order=Max("order"))
                    ["max_order"]
                    or 0
                )

                data["order"] = last_order + 1

            serializer = BudgetSheetStageWriteSerializer(
                data=data,
                context=self._stage_serializer_context(
                    locked_sheet,
                ),
            )
            serializer.is_valid(raise_exception=True)

            try:
                stage = serializer.save(
                    budget_sheet=locked_sheet,
                )
            except IntegrityError as error:
                raise ValidationError(
                    "Não foi possível adicionar a etapa. "
                    "Verifique se ela ou sua posição já existem."
                ) from error

        response_serializer = BudgetSheetStageReadSerializer(
            stage,
            context=self.get_serializer_context(),
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        methods=["PATCH"],
        request=BudgetSheetStageWriteSerializer,
        responses=BudgetSheetStageReadSerializer,
    )
    @extend_schema(
        methods=["DELETE"],
        request=None,
        responses={204: None},
    )
    @action(
        detail=True,
        methods=("patch", "delete"),
        url_path=r"stages/(?P<stage_id>\d+)",
    )
    def stage_detail(
        self,
        request,
        pk=None,
        stage_id=None,
    ):
        budget_sheet = self.get_object()

        try:
            sheet_stage = (
                budget_sheet.stages
                .select_related("stage")
                .get(pk=stage_id)
            )
        except BudgetSheetStage.DoesNotExist as error:
            raise ValidationError(
                {
                    "stage": (
                        "A etapa não pertence a esta planilha."
                    )
                }
            ) from error

        if request.method == "DELETE":
            with transaction.atomic():
                locked_sheet = (
                    BudgetSheet.objects
                    .select_for_update()
                    .get(pk=budget_sheet.pk)
                )
                self._ensure_editable(locked_sheet)

                locked_stage = (
                    BudgetSheetStage.objects
                    .select_for_update()
                    .get(
                        pk=sheet_stage.pk,
                        budget_sheet=locked_sheet,
                    )
                )

                removed_order = locked_stage.order
                locked_stage.delete()

                BudgetSheetStage.objects.filter(
                    budget_sheet=locked_sheet,
                    order__gt=removed_order,
                ).update(order=F("order") - 1)

                recalculate_budget_totals(locked_sheet.pk)

            return Response(status=status.HTTP_204_NO_CONTENT)

        try:
            with transaction.atomic():
                locked_sheet = (
                    BudgetSheet.objects
                    .select_for_update()
                    .get(pk=budget_sheet.pk)
                )
                self._ensure_editable(locked_sheet)

                locked_stage = (
                    BudgetSheetStage.objects
                    .select_for_update()
                    .select_related("stage")
                    .get(
                        pk=sheet_stage.pk,
                        budget_sheet=locked_sheet,
                    )
                )

                serializer = BudgetSheetStageWriteSerializer(
                    locked_stage,
                    data=request.data,
                    partial=True,
                    context=self._stage_serializer_context(
                        locked_sheet,
                    ),
                )
                serializer.is_valid(raise_exception=True)
                updated_stage = serializer.save()
        except IntegrityError as error:
            raise ValidationError(
                "Não foi possível atualizar a etapa. "
                "Verifique a posição informada."
            ) from error

        response_serializer = BudgetSheetStageReadSerializer(
            updated_stage,
            context=self.get_serializer_context(),
        )

        return Response(response_serializer.data)

    @extend_schema(
        request=StageReorderSerializer,
        responses=BudgetSheetStageReadSerializer(many=True),
    )
    @action(
        detail=True,
        methods=("post",),
        url_path="stages/reorder",
    )
    def reorder_stages(
        self,
        request,
        pk=None,
    ):
        budget_sheet = self.get_object()
        self._ensure_editable(budget_sheet)

        raw_stage_ids = request.data.get(
            "stage_ids",
        )

        if not isinstance(raw_stage_ids, list):
            raise ValidationError(
                {
                    "stage_ids": (
                        "Envie a lista ordenada de IDs das "
                        "etapas da planilha."
                    )
                }
            )

        try:
            stage_ids = [
                int(stage_id)
                for stage_id in raw_stage_ids
            ]
        except (TypeError, ValueError) as error:
            raise ValidationError(
                {
                    "stage_ids": (
                        "Todos os IDs devem ser números inteiros."
                    )
                }
            ) from error

        if len(stage_ids) != len(set(stage_ids)):
            raise ValidationError(
                {
                    "stage_ids": (
                        "A lista não pode conter IDs repetidos."
                    )
                }
            )

        with transaction.atomic():
            locked_sheet = (
                BudgetSheet.objects
                .select_for_update()
                .get(pk=budget_sheet.pk)
            )
            self._ensure_editable(locked_sheet)

            stages = list(
                BudgetSheetStage.objects
                .select_for_update()
                .filter(budget_sheet=locked_sheet)
            )

            existing_ids = {
                stage.pk
                for stage in stages
            }

            if set(stage_ids) != existing_ids:
                raise ValidationError(
                    {
                        "stage_ids": (
                            "A lista deve conter exatamente todas "
                            "as etapas desta planilha."
                        )
                    }
                )

            BudgetSheetStage.objects.filter(
                budget_sheet=locked_sheet,
            ).update(
                order=F("order") + 1_000_000,
            )

            stages_by_id = {
                stage.pk: stage
                for stage in stages
            }

            ordered_stages = []

            for order, stage_id in enumerate(
                stage_ids,
                start=1,
            ):
                stage = stages_by_id[stage_id]
                stage.order = order
                ordered_stages.append(stage)

            BudgetSheetStage.objects.bulk_update(
                ordered_stages,
                fields=("order",),
            )

        refreshed_stages = (
            budget_sheet.stages
            .select_related("stage")
            .order_by("order", "id")
        )

        serializer = BudgetSheetStageReadSerializer(
            refreshed_stages,
            many=True,
            context=self.get_serializer_context(),
        )

        return Response(serializer.data)

    @extend_schema(
        methods=["GET"],
        responses=BudgetSheetStageItemSerializer(many=True),
    )
    @extend_schema(
        methods=["POST"],
        request=BudgetSheetStageItemSerializer,
        responses={201: BudgetSheetStageItemSerializer},
    )
    @action(
        detail=True,
        methods=("get", "post"),
        url_path=(
            r"stages/(?P<stage_id>\d+)/items"
        ),
    )
    def stage_items(
        self,
        request,
        pk=None,
        stage_id=None,
    ):
        budget_sheet = self.get_object()

        sheet_stage = self._get_sheet_stage(
            budget_sheet,
            stage_id,
        )

        if request.method == "GET":
            queryset = (
                sheet_stage.items
                .select_related(
                    "service_composition",
                    "supply",
                )
                .order_by("order", "id")
            )

            serializer = BudgetSheetStageItemSerializer(
                queryset,
                many=True,
                context={
                    **self.get_serializer_context(),
                    "budget_sheet_stage": sheet_stage,
                },
            )

            return Response(serializer.data)

        self._ensure_editable(budget_sheet)

        serializer = BudgetSheetStageItemSerializer(
            data=request.data,
            context={
                **self.get_serializer_context(),
                "budget_sheet_stage": sheet_stage,
            },
        )
        serializer.is_valid(raise_exception=True)

        try:
            item = serializer.save()
        except IntegrityError as error:
            raise ValidationError(
                "Não foi possível adicionar o item. "
                "Verifique sua posição."
            ) from error

        response_serializer = BudgetSheetStageItemSerializer(
            item,
            context={
                **self.get_serializer_context(),
                "budget_sheet_stage": sheet_stage,
            },
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        methods=["PATCH"],
        request=BudgetSheetStageItemSerializer,
        responses=BudgetSheetStageItemSerializer,
    )
    @extend_schema(
        methods=["DELETE"],
        request=None,
        responses={204: None},
    )
    @action(
        detail=True,
        methods=("patch", "delete"),
        url_path=(
            r"stages/(?P<stage_id>\d+)"
            r"/items/(?P<item_id>\d+)"
        ),
    )
    def stage_item_detail(
        self,
        request,
        pk=None,
        stage_id=None,
        item_id=None,
    ):
        budget_sheet = self.get_object()

        sheet_stage = self._get_sheet_stage(
            budget_sheet,
            stage_id,
        )

        try:
            item = (
                sheet_stage.items
                .select_related(
                    "service_composition",
                    "supply",
                )
                .get(pk=item_id)
            )
        except BudgetSheetStageItem.DoesNotExist as error:
            raise ValidationError(
                {
                    "item": (
                        "O item não pertence a esta etapa."
                    )
                }
            ) from error

        if request.method == "DELETE":
            self._ensure_editable(budget_sheet)
            delete_stage_item(item)

            return Response(
                status=status.HTTP_204_NO_CONTENT,
            )

        self._ensure_editable(budget_sheet)

        serializer = BudgetSheetStageItemSerializer(
            item,
            data=request.data,
            partial=True,
            context={
                **self.get_serializer_context(),
                "budget_sheet_stage": sheet_stage,
            },
        )
        serializer.is_valid(raise_exception=True)

        try:
            updated_item = serializer.save()
        except IntegrityError as error:
            raise ValidationError(
                "Não foi possível atualizar o item. "
                "Verifique sua posição."
            ) from error

        response_serializer = BudgetSheetStageItemSerializer(
            updated_item,
            context={
                **self.get_serializer_context(),
                "budget_sheet_stage": sheet_stage,
            },
        )

        return Response(response_serializer.data)

    @extend_schema(
        request=ItemReorderSerializer,
        responses=BudgetSheetStageItemSerializer(many=True),
    )
    @action(
        detail=True,
        methods=("post",),
        url_path=(
            r"stages/(?P<stage_id>\d+)"
            r"/items/reorder"
        ),
    )
    def reorder_stage_items_action(
        self,
        request,
        pk=None,
        stage_id=None,
    ):
        budget_sheet = self.get_object()
        self._ensure_editable(budget_sheet)

        sheet_stage = self._get_sheet_stage(
            budget_sheet,
            stage_id,
        )

        raw_item_ids = request.data.get(
            "item_ids",
        )

        if not isinstance(raw_item_ids, list):
            raise ValidationError(
                {
                    "item_ids": (
                        "Envie a lista ordenada de IDs "
                        "dos itens da etapa."
                    )
                }
            )

        try:
            item_ids = []

            for item_id in raw_item_ids:
                if isinstance(item_id, bool):
                    raise ValueError

                item_ids.append(int(item_id))

        except (TypeError, ValueError) as error:
            raise ValidationError(
                {
                    "item_ids": (
                        "Todos os IDs devem ser números inteiros."
                    )
                }
            ) from error

        try:
            items = reorder_stage_items(
                sheet_stage,
                item_ids,
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)

        serializer = BudgetSheetStageItemSerializer(
            items,
            many=True,
            context={
                **self.get_serializer_context(),
                "budget_sheet_stage": sheet_stage,
            },
        )

        return Response(serializer.data)

    @extend_schema(
        request=BudgetCompositionComponentEnabledSerializer,
        responses=BudgetSheetStageItemSerializer,
    )
    @action(
        detail=True,
        methods=("patch",),
        url_path=(
            r"stages/(?P<stage_id>\d+)"
            r"/items/(?P<item_id>\d+)"
            r"/components/enabled"
        ),
    )
    def stage_item_component_enabled(
        self,
        request,
        pk=None,
        stage_id=None,
        item_id=None,
    ):
        budget_sheet = self.get_object()

        sheet_stage = self._get_sheet_stage(
            budget_sheet,
            stage_id,
        )

        try:
            item = (
                sheet_stage.items
                .select_related(
                    "service_composition",
                    "supply",
                )
                .get(pk=item_id)
            )
        except BudgetSheetStageItem.DoesNotExist as error:
            raise ValidationError(
                {
                    "item": (
                        "O item não pertence a esta etapa."
                    )
                }
            ) from error

        input_serializer = BudgetCompositionComponentEnabledSerializer(
            data=request.data,
        )
        input_serializer.is_valid(
            raise_exception=True,
        )

        try:
            updated_item = update_composition_component_enabled(
                item,
                input_serializer.validated_data["source_path"],
                input_serializer.validated_data["enabled"],
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)

        response_serializer = BudgetSheetStageItemSerializer(
            updated_item,
            context={
                **self.get_serializer_context(),
                "budget_sheet_stage": sheet_stage,
            },
        )

        return Response(
            response_serializer.data
        )

    @extend_schema(request=BudgetCompositionCustomizationSerializer, responses=BudgetSheetStageItemSerializer)
    @action(
        detail=True, methods=("patch",),
        url_path=r"stages/(?P<stage_id>\d+)/items/(?P<item_id>\d+)/components/customize",
    )
    def stage_item_components_customize(self, request, pk=None, stage_id=None, item_id=None):
        sheet_stage = self._get_sheet_stage(self.get_object(), stage_id)
        try:
            item = sheet_stage.items.get(pk=item_id)
        except BudgetSheetStageItem.DoesNotExist as error:
            raise ValidationError({"item": "O item não pertence a esta etapa."}) from error
        serializer = BudgetCompositionCustomizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated = customize_budget_composition(item, serializer.validated_data)
        except DjangoValidationError as error:
            raise_api_validation_error(error)
        return Response(BudgetSheetStageItemSerializer(
            updated, context={**self.get_serializer_context(), "budget_sheet_stage": sheet_stage},
        ).data)

    @staticmethod
    def _get_sheet_stage(
        budget_sheet,
        stage_id,
    ):
        try:
            return (
                BudgetSheetStage.objects
                .select_related(
                    "budget_sheet",
                    "stage",
                )
                .get(
                    pk=stage_id,
                    budget_sheet=budget_sheet,
                )
            )
        except BudgetSheetStage.DoesNotExist as error:
            raise ValidationError(
                {
                    "stage": (
                        "A etapa não pertence a esta planilha."
                    )
                }
            ) from error


class LegacyProtectedSoftDeleteMixin:
    legacy_delete_error = "Registros legados são imutáveis."

    def perform_destroy(self, instance) -> None:
        if instance.origin == DataOrigin.LEGACY:
            raise ValidationError(self.legacy_delete_error)

        instance.is_active = False
        instance.save(update_fields=("is_active", "updated_at"))


class SupplyViewSet(
    LegacyProtectedSoftDeleteMixin,
    FilteredViewSetMixin,
    viewsets.ModelViewSet,
):
    queryset = supply_queryset()
    serializer_class = SupplySerializer
    pagination_class = SupplyPagination
    legacy_delete_error = "Insumos legados são imutáveis."

    search_fields = (
        "description",
        "full_description",
    )

    ordering_fields = (
        "description",
        "updated_at",
    )

    ordering = (
        "description",
        "id",
    )

    filterset_fields = (
        "origin",
        "supply_type",
        "is_active",
        "unit",
        "unit_measure",
        "material_group",
    )

    autocomplete_min_length = 3

    def get_serializer_class(self):
        if self.action == "autocomplete":
            return SupplyAutocompleteSerializer

        return SupplySerializer

    def perform_create(self, serializer):
        serializer.save(
            created_by=self.request.user,
        )

    def perform_update(self, serializer):
        serializer.save(
            updated_by=self.request.user,
        )

    @action(
        detail=False,
        methods=("get",),
        url_path="autocomplete",
        pagination_class=SupplyAutocompletePagination,
    )
    def autocomplete(self, request):
        term = request.query_params.get(
            "search",
            "",
        ).strip()

        queryset = self.get_queryset().filter(
            is_active=True,
        )

        if term:
            if len(term) < self.autocomplete_min_length:
                queryset = queryset.none()
            else:
                queryset = queryset.filter(
                    Q(description__icontains=term)
                    | Q(full_description__icontains=term)
                    | Q(specification__icontains=term)
                )

        supply_filter = SupplyAutocompleteFilter(
            data=request.query_params,
            queryset=queryset,
        )

        if not supply_filter.is_valid():
            raise ValidationError(
                supply_filter.errors,
            )

        queryset = supply_filter.qs.order_by(
            "description",
            "id",
        )

        page = self.paginate_queryset(
            queryset,
        )

        serializer = self.get_serializer(
            page,
            many=True,
        )

        return self.get_paginated_response(
            serializer.data,
        )


class ServiceCompositionGroupViewSet(FilteredViewSetMixin, viewsets.ModelViewSet):
    queryset = ServiceCompositionGroup.objects.select_related("parent").all()
    serializer_class = ServiceCompositionGroupSerializer
    pagination_class = None
    search_fields = ("code", "name")
    ordering_fields = ("code", "name", "updated_at")
    ordering = ("code", "name", "id")
    filterset_fields = ("parent", "is_active")

    def perform_destroy(self, instance):
        if instance.children.filter(is_active=True).exists():
            raise ValidationError({"detail": "Desative primeiro os subgrupos ativos."})
        if instance.compositions.filter(is_active=True).exists():
            raise ValidationError({"detail": "Reclassifique primeiro as composições ativas."})
        instance.is_active = False
        instance.save(update_fields=("is_active", "updated_at"))

    @action(detail=False, methods=("get",), url_path="tree")
    def tree(self, request):
        groups = list(self.filter_queryset(self.get_queryset().filter(is_active=True)))
        nodes = {g.pk: {"id": g.pk, "code": g.code, "name": g.name,
                        "parent": g.parent_id, "children": []} for g in groups}
        roots = []
        for group in groups:
            node = nodes[group.pk]
            if group.parent_id in nodes:
                nodes[group.parent_id]["children"].append(node)
            else:
                roots.append(node)
        return Response(roots)


class ServiceCompositionViewSet(
    LegacyProtectedSoftDeleteMixin,
    FilteredViewSetMixin,
    viewsets.ModelViewSet,
):
    queryset = service_composition_queryset()
    serializer_class = ServiceCompositionReadSerializer
    legacy_delete_error = "Composições legadas são imutáveis."

    search_fields = (
        "name",
        "code",
    )

    ordering_fields = (
        "name",
        "code",
        "updated_at",
    )

    # O ranking é anotado em get_queryset(). Com isso, uma composição cujo
    # nome/código corresponde exatamente ao texto pesquisado vem antes das
    # correspondências parciais. Isso é importante porque a Planilha também
    # pesquisa Supplies do tipo SERVICE e os dois catálogos podem ter o mesmo nome.
    ordering = (
        "_search_rank",
        "name",
        "id",
    )

    filterset_fields = (
        "origin",
        "is_active",
        "group",
    )

    def get_queryset(self):
        queryset = service_composition_queryset()
        term = self.request.query_params.get("search", "").strip()

        if not term:
            return queryset.annotate(
                _search_rank=Value(2, output_field=IntegerField()),
            )

        return queryset.annotate(
            _search_rank=Case(
                When(name__iexact=term, then=Value(0)),
                When(code__iexact=term, then=Value(0)),
                When(name__istartswith=term, then=Value(1)),
                When(code__istartswith=term, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            ),
        )

    def get_serializer_class(self):
        serializer_by_action = {
            "create": ServiceCompositionWriteSerializer,
            "update": ServiceCompositionWriteSerializer,
            "partial_update": ServiceCompositionWriteSerializer,
        }

        return serializer_by_action.get(
            self.action,
            ServiceCompositionReadSerializer,
        )

    @action(detail=True, methods=("patch",), url_path="classify")
    def classify(self, request, pk=None):
        composition = self.get_object()
        group_id = request.data.get("group", None)
        if group_id is None:
            group = None
        else:
            try:
                group = ServiceCompositionGroup.objects.get(pk=group_id, is_active=True)
            except (ServiceCompositionGroup.DoesNotExist, ValueError, TypeError):
                raise ValidationError({"group": "Grupo inválido ou inativo."})
        composition.group = group
        composition.save(update_fields=("group", "updated_at"))
        return Response(self.get_serializer(composition).data)

    @action(
        detail=True,
        methods=("post",),
    )
    def publish(self, request, pk=None):
        try:
            version = publish_composition(
                self.get_object()
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)

        serializer = CompositionVersionSerializer(
            version,
            context=self.get_serializer_context(),
        )

        return Response(serializer.data)

    @action(
        detail=True,
        methods=("post",),
        url_path="new-version",
    )
    def new_version(self, request, pk=None):
        try:
            version = create_new_version(
                self.get_object()
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)

        serializer = CompositionVersionSerializer(
            version,
            context=self.get_serializer_context(),
        )

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
        )


class SupplyTypeViewSet(viewsets.ViewSet):
    serializer_class = SupplyTypeSerializer

    def list(self, request):
        items = [
            {
                "value": value,
                "label": label,
            }
            for value, label in SupplyType.choices
        ]

        serializer = self.serializer_class(
            items,
            many=True,
        )

        return Response(serializer.data)


class UnitMeasureViewSet(
    FilteredViewSetMixin,
    viewsets.ReadOnlyModelViewSet,
):
    serializer_class = UnidadeMedidaSerializer
    pagination_class = None

    search_fields = (
        "nome",
        "sigla",
    )

    ordering_fields = (
        "legacy_id",
        "nome",
        "sigla",
    )

    ordering = (
        "legacy_id",
        "nome",
    )

    def get_queryset(self):
        return UnitMeasure.objects.filter(
            ativo=True,
        )


class MaterialGroupViewSet(
    FilteredViewSetMixin,
    viewsets.ReadOnlyModelViewSet,
):
    serializer_class = GrupoMaterialSerializer
    pagination_class = None

    search_fields = (
        "nome",
    )

    ordering_fields = (
        "legacy_id",
        "nome",
    )

    ordering = (
        "legacy_id",
        "nome",
    )

    def get_queryset(self):
        return MaterialGroup.objects.filter(
            ativo=True,
        )