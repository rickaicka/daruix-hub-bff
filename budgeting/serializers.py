from decimal import Decimal
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from django.db import transaction
from django.db.models import Max

from .api_utils import raise_api_validation_error
from .choices import (
    BudgetSheetItemType,
    BudgetSheetStatus,
    CompositionItemType,
    DataOrigin,
    SupplyType,
)
from .models import (
    BudgetSheet,
    BudgetSheetStage,
    BudgetSheetStageItem,
    BudgetStageCatalog,
    MaterialGroup,
    ServiceComposition,
    ServiceCompositionItem,
    ServiceCompositionVersion,
    Supply,
    UnitMeasure,
)
from .services.compositions import create_composition, update_draft
from .services.budget_sheets import (
    build_composition_snapshot,
    ensure_budget_sheet_editable,
    is_current_revision,
    next_stage_item_order,
    recalculate_budget_totals,
)
from .services.budget_costs import bdi_is_configured

class SupplySerializer(serializers.ModelSerializer):
    unit_measure_name = serializers.CharField(
        source="unit_measure.nome",
        read_only=True,
        allow_null=True,
    )
    unit_measure_abbreviation = serializers.CharField(
        source="unit_measure.sigla",
        read_only=True,
        allow_null=True,
    )
    material_group_name = serializers.CharField(
        source="material_group.nome",
        read_only=True,
        allow_null=True,
    )

    created_by = serializers.SerializerMethodField()
    updated_by = serializers.SerializerMethodField()

    class Meta:
        model = Supply
        fields = (
            "id",
            "origin",
            "legacy_id",
            "description",
            "full_description",
            "supply_type",
            "unit",
            "unit_measure",
            "unit_measure_name",
            "unit_measure_abbreviation",
            "material_group",
            "material_group_name",
            "specification",
            "is_active",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "origin",
            "legacy_id",
            "unit",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )

    def get_created_by(self, obj):
        return self._serialize_user(obj.created_by)

    def get_updated_by(self, obj):
        return self._serialize_user(obj.updated_by)

    @staticmethod
    def _serialize_user(user):
        if user is None:
            return None

        nome = getattr(user, "nome", None)

        if not nome and hasattr(user, "get_full_name"):
            nome = user.get_full_name()

        return {
            "id": getattr(user, "id_usuario", user.pk),
            "username": user.get_username(),
            "nome": nome or user.get_username(),
            "email": getattr(user, "email", ""),
        }

    def validate(self, attrs):
        if self.instance:
            immutable_fields = (
                "specification",
                "description",
                "full_description",
                "unit_measure",
            )

            changed_immutable_fields = [
                field
                for field in immutable_fields
                if field in attrs
                   and attrs[field] != getattr(self.instance, field)
            ]

            if changed_immutable_fields:
                raise serializers.ValidationError(
                    {
                        field: "Este campo não pode ser alterado após o cadastro."
                        for field in changed_immutable_fields
                    }
                )

        unit_measure = attrs.get("unit_measure", serializers.empty)

        if unit_measure is not serializers.empty:
            if unit_measure is not None and not unit_measure.ativo:
                raise serializers.ValidationError(
                    {
                        "unit_measure": "A unidade de medida está inativa.",
                    }
                )

            attrs["unit"] = unit_measure.sigla if unit_measure else ""

        material_group = attrs.get("material_group", serializers.empty)

        if (
                material_group is not serializers.empty
                and material_group is not None
                and not material_group.ativo
        ):
            raise serializers.ValidationError(
                {
                    "material_group": "O grupo de material está inativo.",
                }
            )

        return attrs

    def create(self, validated_data):
        return Supply.objects.create(
            origin=DataOrigin.HUB,
            **validated_data,
        )


class CompositionItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(
        max_digits=24,
        decimal_places=4,
        read_only=True,
    )

    class Meta:
        model = ServiceCompositionItem
        fields = (
            "id",
            "item_type",
            "supply",
            "subcomposition",
            "description_snapshot",
            "unit_snapshot",
            "coefficient",
            "material_unit_price",
            "labor_unit_price",
            "equipment_unit_price",
            "position",
            "subtotal",
        )
        read_only_fields = ("id", "subtotal")

    def validate(self, attrs):
        item_type = attrs.get("item_type", CompositionItemType.SUPPLY)
        supply = attrs.get("supply")
        subcomposition = attrs.get("subcomposition")

        if item_type == CompositionItemType.SUPPLY:
            if supply is None:
                raise serializers.ValidationError(
                    {"supply": "O insumo é obrigatório para este tipo de item."}
                )
            if subcomposition is not None:
                raise serializers.ValidationError(
                    {
                        "subcomposition": (
                            "Um item de insumo não pode ter subcomposição."
                        )
                    }
                )
        elif item_type == CompositionItemType.SUBCOMPOSITION:
            if subcomposition is None:
                raise serializers.ValidationError(
                    {
                        "subcomposition": (
                            "A subcomposição é obrigatória para este tipo de item."
                        )
                    }
                )
            if supply is not None:
                raise serializers.ValidationError(
                    {"supply": "Um item de subcomposição não pode ter insumo."}
                )
        elif supply is not None or subcomposition is not None:
            raise serializers.ValidationError(
                "Um item livre não pode apontar para insumo ou subcomposição."
            )

        numeric_fields = (
            "coefficient",
            "material_unit_price",
            "labor_unit_price",
            "equipment_unit_price",
        )
        field_errors = {
            field_name: "O valor não pode ser negativo."
            for field_name in numeric_fields
            if attrs.get(field_name, 0) < 0
        }
        if field_errors:
            raise serializers.ValidationError(field_errors)

        return attrs


class CompositionVersionSerializer(serializers.ModelSerializer):
    items = CompositionItemSerializer(many=True, read_only=True)

    class Meta:
        model = ServiceCompositionVersion
        fields = (
            "id",
            "number",
            "status",
            "origin",
            "unit",
            "material_total",
            "labor_total",
            "equipment_total",
            "total",
            "imported_at",
            "published_at",
            "items",
        )


class ServiceCompositionReadSerializer(serializers.ModelSerializer):
    latest_version = serializers.SerializerMethodField()

    class Meta:
        model = ServiceComposition
        fields = (
            "id",
            "origin",
            "legacy_id",
            "code",
            "name",
            "is_active",
            "latest_version",
            "created_at",
            "updated_at",
        )

    @extend_schema_field(CompositionVersionSerializer(allow_null=True))
    def get_latest_version(self, obj):
        version = obj.latest_version
        if version is None:
            return None

        return CompositionVersionSerializer(
            version,
            context=self.context,
        ).data


class ServiceCompositionWriteSerializer(serializers.ModelSerializer):
    unit = serializers.CharField(
        max_length=30,
        allow_blank=True,
        write_only=True,
    )
    items = CompositionItemSerializer(many=True, write_only=True)

    class Meta:
        model = ServiceComposition
        fields = (
            "id",
            "code",
            "name",
            "is_active",
            "unit",
            "items",
        )
        read_only_fields = ("id",)

    def create(self, validated_data):
        try:
            return create_composition(validated_data)
        except DjangoValidationError as error:
            raise_api_validation_error(error)

    def update(self, instance, validated_data):
        try:
            return update_draft(instance, validated_data)
        except DjangoValidationError as error:
            raise_api_validation_error(error)

    def to_representation(self, instance):
        return ServiceCompositionReadSerializer(
            instance,
            context=self.context,
        ).data


class UnidadeMedidaSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitMeasure
        fields = (
            "id",
            "legacy_id",
            "nome",
            "sigla",
        )
        read_only_fields = fields


class GrupoMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaterialGroup
        fields = (
            "id",
            "legacy_id",
            "nome",
        )
        read_only_fields = fields

class BudgetStageCatalogSerializer(serializers.ModelSerializer):
    class Meta:
        model = BudgetStageCatalog
        fields = (
            "id",
            "origin",
            "legacy_source",
            "legacy_id",
            "code",
            "name",
            "legacy_category",
            "is_active",
        )
        read_only_fields = fields


class BudgetStageCatalogCreateSerializer(serializers.ModelSerializer):
    legacy_category = serializers.ChoiceField(
        choices=(
            ("OPERATIONAL", "Operacional"),
            ("ADMINISTRATIVE", "Administrativa"),
        ),
    )

    class Meta:
        model = BudgetStageCatalog
        fields = (
            "id",
            "origin",
            "legacy_source",
            "legacy_id",
            "code",
            "name",
            "legacy_category",
            "is_active",
        )
        read_only_fields = (
            "id",
            "origin",
            "legacy_source",
            "legacy_id",
            "is_active",
        )

    def validate_name(self, value):
        name = value.strip()

        if len(name) < 3:
            raise serializers.ValidationError(
                "Informe um nome com pelo menos 3 caracteres."
            )

        if BudgetStageCatalog.objects.filter(
            name__iexact=name,
        ).exists():
            raise serializers.ValidationError(
                "Já existe uma etapa com este nome."
            )

        return name

    def validate_code(self, value):
        return value.strip()

    def create(self, validated_data):
        return BudgetStageCatalog.objects.create(
            origin=DataOrigin.HUB,
            legacy_source="",
            legacy_id=None,
            legacy_key="",
            is_active=True,
            **validated_data,
        )


class BudgetSheetStageItemReadSerializer(serializers.ModelSerializer):
    service_composition_name = serializers.CharField(
        source="service_composition.name",
        read_only=True,
        allow_null=True,
    )
    supply_name = serializers.CharField(
        source="supply.description",
        read_only=True,
        allow_null=True,
    )
    supply_type = serializers.CharField(
        source="supply.supply_type",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = BudgetSheetStageItem
        fields = (
            "id",
            "item_type",
            "service_composition",
            "service_composition_name",
            "supply",
            "supply_name",
            "supply_type",
            "description_snapshot",
            "unit_snapshot",
            "quantity",
            "unit_price",
            "unit_discount",
            "subtotal",
            "order",
            "notes",
            "composition_version_number",
            "material_unit_cost",
            "labor_unit_cost",
            "equipment_unit_cost",
            "unit_cost",
            "pricing_factor",
            "apply_bdi",
            "composition_snapshot",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class BudgetSheetStageReadSerializer(serializers.ModelSerializer):
    stage_detail = BudgetStageCatalogSerializer(
        source="stage",
        read_only=True,
    )
    items = BudgetSheetStageItemReadSerializer(
        many=True,
        read_only=True,
    )
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = BudgetSheetStage
        fields = (
            "id",
            "item_count",
            "items",
            "stage",
            "stage_detail",
            "order",
            "name_snapshot",
            "notes",
            "subtotal",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_item_count(self, obj) -> int:
        prefetched_items = getattr(
            obj,
            "_prefetched_objects_cache",
            {},
        ).get("items")

        if prefetched_items is not None:
            return len(prefetched_items)

        return obj.items.count()

class BudgetSheetStageWriteSerializer(serializers.ModelSerializer):
    order = serializers.IntegerField(
        min_value=1,
        required=False,
    )
    stage_detail = BudgetStageCatalogSerializer(
        source="stage",
        read_only=True,
    )

    class Meta:
        model = BudgetSheetStage
        fields = (
            "id",
            "budget_sheet",
            "stage",
            "stage_detail",
            "order",
            "name_snapshot",
            "notes",
            "subtotal",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "budget_sheet",
            "stage_detail",
            "name_snapshot",
            "subtotal",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        budget_sheet = self.context.get(
            "budget_sheet",
        )

        if budget_sheet is None:
            raise serializers.ValidationError(
                "A planilha de orçamento não foi informada."
            )

        stage = attrs.get(
            "stage",
            self.instance.stage if self.instance else None,
        )
        order = attrs.get(
            "order",
            self.instance.order if self.instance else None,
        )

        errors = {}

        stage_was_changed = (
            self.instance is None
            or (
                stage is not None
                and stage.pk != self.instance.stage_id
            )
        )

        if (
            stage is not None
            and not stage.is_active
            and stage_was_changed
        ):
            errors["stage"] = (
                "Uma etapa inativa não pode ser adicionada "
                "ao orçamento."
            )

        existing_stages = BudgetSheetStage.objects.filter(
            budget_sheet=budget_sheet,
        )

        if self.instance is not None:
            existing_stages = existing_stages.exclude(
                pk=self.instance.pk,
            )

        if (
            stage is not None
            and existing_stages.filter(stage=stage).exists()
        ):
            errors["stage"] = (
                "Esta etapa já foi adicionada ao orçamento."
            )

        if (
            order is not None
            and existing_stages.filter(order=order).exists()
        ):
            errors["order"] = (
                "Já existe uma etapa nesta posição."
            )

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def create(self, validated_data):
        stage = validated_data["stage"]
        validated_data["name_snapshot"] = stage.name

        try:
            return super().create(validated_data)
        except DjangoValidationError as error:
            raise_api_validation_error(error)

    def update(self, instance, validated_data):
        stage = validated_data.get(
            "stage",
            instance.stage,
        )

        if stage.pk != instance.stage_id:
            validated_data["name_snapshot"] = stage.name

        try:
            return super().update(
                instance,
                validated_data,
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)


class BudgetSheetStageItemSerializer(
    serializers.ModelSerializer
):
    order = serializers.IntegerField(
        min_value=1,
        required=False,
    )
    description_snapshot = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
    )
    unit_snapshot = serializers.CharField(
        max_length=30,
        required=False,
        allow_blank=True,
    )
    service_composition_name = serializers.CharField(
        source="service_composition.name",
        read_only=True,
        allow_null=True,
    )
    supply_name = serializers.CharField(
        source="supply.description",
        read_only=True,
        allow_null=True,
    )
    supply_type = serializers.CharField(
        source="supply.supply_type",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = BudgetSheetStageItem
        fields = (
            "id",
            "budget_sheet_stage",
            "item_type",
            "service_composition",
            "service_composition_name",
            "supply",
            "supply_name",
            "supply_type",
            "description_snapshot",
            "unit_snapshot",
            "quantity",
            "unit_price",
            "unit_discount",
            "subtotal",
            "order",
            "notes",
            "composition_version_number",
            "material_unit_cost",
            "labor_unit_cost",
            "equipment_unit_cost",
            "unit_cost",
            "pricing_factor",
            "apply_bdi",
            "composition_snapshot",
            "origin",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "budget_sheet_stage",
            "service_composition_name",
            "supply_name",
            "supply_type",
            "subtotal",
            "composition_version_number",
            "material_unit_cost",
            "labor_unit_cost",
            "equipment_unit_cost",
            "unit_cost",
            "pricing_factor",
            "composition_snapshot",
            "origin",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        budget_sheet_stage = self.context.get(
            "budget_sheet_stage",
        )

        if budget_sheet_stage is None:
            raise serializers.ValidationError(
                "A etapa da planilha não foi informada."
            )

        item_type = attrs.get(
            "item_type",
            (
                self.instance.item_type
                if self.instance
                else BudgetSheetItemType.SERVICE_COMPOSITION
            ),
        )
        service_composition = attrs.get(
            "service_composition",
            (
                self.instance.service_composition
                if self.instance
                else None
            ),
        )
        supply = attrs.get(
            "supply",
            self.instance.supply if self.instance else None,
        )
        description = attrs.get(
            "description_snapshot",
            (
                self.instance.description_snapshot
                if self.instance
                else ""
            ),
        )
        order = attrs.get(
            "order",
            self.instance.order if self.instance else None,
        )

        errors = {}
        discount = attrs.get("unit_discount", self.instance.unit_discount if self.instance else Decimal("0"))
        if discount < 0:
            errors["unit_discount"] = "O desconto não pode ser negativo."
        if item_type == BudgetSheetItemType.FREE_TEXT and discount:
            errors["unit_discount"] = "Desconto unitário disponível para insumos e composições."


        if (
            item_type
            == BudgetSheetItemType.SERVICE_COMPOSITION
        ):
            if service_composition is None:
                errors["service_composition"] = (
                    "A composição de serviço é obrigatória."
                )
            elif not service_composition.is_active:
                errors["service_composition"] = (
                    "A composição selecionada está inativa."
                )

            if (
                "supply" in attrs
                and attrs["supply"] is not None
            ):
                errors["supply"] = (
                    "Um item de composição não pode possuir "
                    "um insumo direto."
                )
            else:
                attrs["supply"] = None

        elif item_type == BudgetSheetItemType.SUPPLY:
            if supply is None:
                errors["supply"] = (
                    "O insumo é obrigatório."
                )
            elif not supply.is_active:
                errors["supply"] = (
                    "O insumo selecionado está inativo."
                )

            if (
                "service_composition" in attrs
                and attrs["service_composition"] is not None
            ):
                errors["service_composition"] = (
                    "Um item de insumo não pode possuir "
                    "uma composição."
                )
            else:
                attrs["service_composition"] = None

        elif item_type == BudgetSheetItemType.FREE_TEXT:
            attrs["apply_bdi"] = False
            attrs["service_composition"] = None
            attrs["supply"] = None

            if not str(description or "").strip():
                errors["description_snapshot"] = (
                    "A descrição do item livre é obrigatória."
                )

        else:
            errors["item_type"] = (
                "O tipo de item informado é inválido."
            )

        apply_bdi = attrs.get(
            "apply_bdi",
            self.instance.apply_bdi if self.instance else False,
        )
        if (
            item_type in (BudgetSheetItemType.SERVICE_COMPOSITION, BudgetSheetItemType.SUPPLY)
            and apply_bdi
            and not bdi_is_configured(budget_sheet_stage.budget_sheet)
        ):
            errors["apply_bdi"] = (
                "Configure o BDI desta revisão antes de aplicá-lo à composição."
            )

        existing_items = (
            BudgetSheetStageItem.objects
            .filter(
                budget_sheet_stage=budget_sheet_stage,
            )
        )

        if self.instance is not None:
            existing_items = existing_items.exclude(
                pk=self.instance.pk,
            )

        if (
            order is not None
            and existing_items.filter(order=order).exists()
        ):
            errors["order"] = (
                "Já existe um item nesta posição."
            )

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    @staticmethod
    def _supply_snapshot(
        supply,
    ) -> tuple[str, str]:
        unit = (
            supply.unit_measure.sigla
            if getattr(supply, "unit_measure_id", None)
            else supply.unit
        )
        return (
            supply.description,
            unit or "",
        )

    def _apply_snapshot(
        self,
        validated_data,
        *,
        instance=None,
    ):
        item_type = validated_data.get(
            "item_type",
            (
                instance.item_type
                if instance
                else BudgetSheetItemType.SERVICE_COMPOSITION
            ),
        )

        if item_type == BudgetSheetItemType.SERVICE_COMPOSITION:
            composition = validated_data.get(
                "service_composition",
                instance.service_composition if instance else None,
            )
            reference_changed = (
                instance is None
                or instance.item_type != item_type
                or (
                    composition is not None
                    and composition.pk != instance.service_composition_id
                )
            )

            if reference_changed and composition is not None:
                snapshot = build_composition_snapshot(composition)
                validated_data["description_snapshot"] = composition.name
                validated_data["unit_snapshot"] = snapshot["unit"] or ""
                validated_data["composition_version_number"] = snapshot[
                    "version_number"
                ]
                validated_data["material_unit_cost"] = Decimal(
                    snapshot["material_total"]
                )
                validated_data["labor_unit_cost"] = Decimal(
                    snapshot["labor_total"]
                )
                validated_data["equipment_unit_cost"] = Decimal(
                    snapshot["equipment_total"]
                )
                validated_data["unit_cost"] = Decimal(snapshot["total"])
                validated_data["composition_snapshot"] = snapshot
                validated_data["supply"] = None

                # A composição é a fonte de verdade financeira. O orçamento
                # escolhe somente o multiplicador (quantity); preço/unidade e
                # componentes vêm sempre do snapshot da versão selecionada.
                validated_data["unit_price"] = Decimal(snapshot["total"])

            elif instance is not None:
                # Ao editar uma composição já inserida, preserve integralmente
                # o snapshot. Mesmo que o cliente envie estes campos, somente
                # quantity (além de metadados como order/notes) pode afetar o
                # cálculo financeiro da linha pai.
                validated_data["description_snapshot"] = instance.description_snapshot
                validated_data["unit_snapshot"] = instance.unit_snapshot
                validated_data["unit_price"] = instance.unit_cost
                validated_data["supply"] = None

        elif item_type == BudgetSheetItemType.SUPPLY:
            supply = validated_data.get(
                "supply",
                instance.supply if instance else None,
            )
            reference_changed = (
                instance is None
                or instance.item_type != item_type
                or (
                    supply is not None
                    and supply.pk != instance.supply_id
                )
            )

            if reference_changed and supply is not None:
                description, unit = self._supply_snapshot(supply)
                validated_data["description_snapshot"] = description
                validated_data["unit_snapshot"] = unit
                validated_data["service_composition"] = None
                validated_data["composition_version_number"] = None
                validated_data["material_unit_cost"] = 0
                validated_data["labor_unit_cost"] = 0
                validated_data["equipment_unit_cost"] = 0
                validated_data["unit_cost"] = 0
                validated_data["pricing_factor"] = 0
                validated_data["composition_snapshot"] = {}

            # Para insumos diretos, unit_price no payload representa o custo
            # informado. No retorno ele é o preço de venda recalculado.
            # PATCH somente de BDI/quantidade preserva a base anterior.
            base = Decimal(validated_data.get(
                "unit_price", instance.unit_cost if instance else 0,
            ))
            validated_data["unit_cost"] = base
            validated_data["material_unit_cost"] = base if supply and supply.supply_type != SupplyType.LABOR else 0
            validated_data["labor_unit_cost"] = base if supply and supply.supply_type == SupplyType.LABOR else 0
            validated_data["equipment_unit_cost"] = 0

        elif item_type == BudgetSheetItemType.FREE_TEXT:
            # Ao converter uma composição/insumo em item livre, nenhum snapshot
            # interno da referência anterior pode sobreviver.
            validated_data["service_composition"] = None
            validated_data["supply"] = None
            validated_data["composition_version_number"] = None
            validated_data["material_unit_cost"] = 0
            validated_data["labor_unit_cost"] = 0
            validated_data["equipment_unit_cost"] = 0
            validated_data["unit_cost"] = 0
            validated_data["pricing_factor"] = 0
            validated_data["composition_snapshot"] = {}

    def create(self, validated_data):
        try:
            with transaction.atomic():
                context_stage = self.context["budget_sheet_stage"]

                # BudgetSheet é o lock do agregado. Todas as mutações de uma
                # planilha seguem a ordem sheet -> stage/item, evitando
                # deadlocks com finalização/revisão concorrente.
                locked_sheet = (
                    BudgetSheet.objects
                    .select_for_update()
                    .get(pk=context_stage.budget_sheet_id)
                )
                ensure_budget_sheet_editable(locked_sheet)

                budget_sheet_stage = (
                    BudgetSheetStage.objects
                    .select_for_update()
                    .get(
                        pk=context_stage.pk,
                        budget_sheet=locked_sheet,
                    )
                )

                if "order" not in validated_data:
                    validated_data["order"] = next_stage_item_order(
                        budget_sheet_stage,
                    )

                self._apply_snapshot(validated_data)

                item = BudgetSheetStageItem.objects.create(
                    budget_sheet_stage=budget_sheet_stage,
                    origin=DataOrigin.HUB,
                    **validated_data,
                )

                recalculate_budget_totals(locked_sheet.pk)
                item.refresh_from_db()
                return item

        except DjangoValidationError as error:
            raise_api_validation_error(error)

    def update(self, instance, validated_data):
        try:
            with transaction.atomic():
                sheet_id = instance.budget_sheet_stage.budget_sheet_id
                locked_sheet = (
                    BudgetSheet.objects
                    .select_for_update()
                    .get(pk=sheet_id)
                )
                ensure_budget_sheet_editable(locked_sheet)

                # PostgreSQL não permite FOR UPDATE sobre o lado anulável
                # de OUTER JOIN. service_composition e supply são FKs opcionais,
                # portanto o lock precisa atingir somente a linha base do item.
                # As relações necessárias são carregadas de forma lazy dentro
                # desta mesma transação por _apply_snapshot().
                locked_instance = (
                    BudgetSheetStageItem.objects
                    .select_for_update()
                    .get(
                        pk=instance.pk,
                        budget_sheet_stage__budget_sheet=locked_sheet,
                    )
                )

                self._apply_snapshot(
                    validated_data,
                    instance=locked_instance,
                )
                item = super().update(
                    locked_instance,
                    validated_data,
                )

                recalculate_budget_totals(locked_sheet.pk)
                item.refresh_from_db()
                return item

        except DjangoValidationError as error:
            raise_api_validation_error(error)

class BudgetCompositionComponentEnabledSerializer(
    serializers.Serializer
):
    source_path = serializers.RegexField(
        regex=r"^\d+(?:\.\d+)*$",
        max_length=120,
        trim_whitespace=True,
        error_messages={
            "required": (
                "Informe o componente da composição."
            ),
            "blank": (
                "Informe o componente da composição."
            ),
            "invalid": (
                "Informe um caminho de componente válido."
            ),
            "max_length": (
                "O caminho do componente é muito longo."
            ),
        },
    )

    enabled = serializers.BooleanField(
        required=True,
        error_messages={
            "required": (
                "Informe se o componente deve ser "
                "utilizado na planilha."
            ),
            "invalid": (
                "Informe verdadeiro ou falso para "
                "habilitar/desabilitar o componente."
            ),
        },
    )

    def validate_source_path(
        self,
        value: str,
    ) -> str:
        return str(value or "").strip()

class BudgetCompositionComponentUpdateSerializer(serializers.Serializer):
    source_path = serializers.RegexField(regex=r"^\d+(?:\.\d+)*$", max_length=120)
    quantity = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0.000001"), required=False)
    material_unit_price = serializers.DecimalField(max_digits=22, decimal_places=8, min_value=Decimal("0"), required=False)
    labor_unit_price = serializers.DecimalField(max_digits=22, decimal_places=8, min_value=Decimal("0"), required=False)
    equipment_unit_price = serializers.DecimalField(max_digits=22, decimal_places=8, min_value=Decimal("0"), required=False)


class BudgetCompositionComponentAdditionSerializer(serializers.Serializer):
    parent_path = serializers.RegexField(regex=r"^\d+(?:\.\d+)*$", max_length=120, required=False, allow_blank=True, default="")
    item_type = serializers.ChoiceField(choices=CompositionItemType.choices)
    supply = serializers.PrimaryKeyRelatedField(queryset=Supply.objects.filter(is_active=True), required=False, allow_null=True)
    subcomposition = serializers.PrimaryKeyRelatedField(queryset=ServiceComposition.objects.filter(is_active=True), required=False, allow_null=True)
    description_snapshot = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    unit_snapshot = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    quantity = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0.000001"))
    material_unit_price = serializers.DecimalField(max_digits=22, decimal_places=8, min_value=Decimal("0"), required=False, default=Decimal("0"))
    labor_unit_price = serializers.DecimalField(max_digits=22, decimal_places=8, min_value=Decimal("0"), required=False, default=Decimal("0"))
    equipment_unit_price = serializers.DecimalField(max_digits=22, decimal_places=8, min_value=Decimal("0"), required=False, default=Decimal("0"))

    def validate(self, attrs):
        kind = attrs["item_type"]
        supply, subcomposition = attrs.get("supply"), attrs.get("subcomposition")
        if kind == CompositionItemType.SUPPLY and (not supply or subcomposition):
            raise serializers.ValidationError("Selecione somente um insumo para este componente.")
        if kind == CompositionItemType.SUBCOMPOSITION and (not subcomposition or supply):
            raise serializers.ValidationError("Selecione somente uma subcomposição para este componente.")
        if kind == CompositionItemType.FREE_TEXT and (supply or subcomposition or not attrs["description_snapshot"].strip()):
            raise serializers.ValidationError("Informe a descrição do item livre, sem referência ao catálogo.")
        return attrs


class BudgetCompositionCustomizationSerializer(serializers.Serializer):
    expected_snapshot = serializers.JSONField()
    expected_quantity = serializers.DecimalField(max_digits=18, decimal_places=6)
    updates = BudgetCompositionComponentUpdateSerializer(many=True, required=False, default=list)
    removed_paths = serializers.ListField(child=serializers.RegexField(regex=r"^\d+(?:\.\d+)*$", max_length=120), required=False, default=list, max_length=2000)
    additions = BudgetCompositionComponentAdditionSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        if len(attrs["updates"]) > 2000 or len(attrs["additions"]) > 2000:
            raise serializers.ValidationError("Personalize no máximo 2000 componentes por operação.")
        return attrs


class BudgetSheetSerializer(serializers.ModelSerializer):
    number = serializers.CharField(
        read_only=True,
    )
    proposal_code = serializers.CharField(
        source="proposal.code",
        read_only=True,
        allow_null=True,
    )
    party_name = serializers.SerializerMethodField()
    department_name = serializers.CharField(
        source="department.name",
        read_only=True,
        allow_null=True,
    )
    stages = BudgetSheetStageReadSerializer(
        many=True,
        read_only=True,
    )
    stage_count = serializers.SerializerMethodField()
    is_current = serializers.SerializerMethodField()
    is_editable = serializers.SerializerMethodField()
    revision_root_id = serializers.IntegerField(
        source="revision_group_root_id",
        read_only=True,
    )
    bdi_configured = serializers.SerializerMethodField()

    class Meta:
        model = BudgetSheet
        fields = (
            "id",
            "proposal",
            "proposal_code",
            "party",
            "party_name",
            "department",
            "department_name",
            "number",
            "proposal_sequence",
            "revision",
            "revision_root_id",
            "previous_revision",
            "revision_reason",
            "reference_date",
            "considerations",
            "bdi_percentage",
            "bdi_configured",
            "status",
            "total_amount",
            "stage_count",
            "stages",
            "is_current",
            "is_editable",
            "finalized_by",
            "finalized_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "proposal_code",
            "party_name",
            "department_name",
            "proposal_sequence",
            "revision",
            "revision_root_id",
            "previous_revision",
            "revision_reason",
            "bdi_percentage",
            "bdi_configured",
            "status",
            "total_amount",
            "stage_count",
            "stages",
            "is_current",
            "is_editable",
            "finalized_by",
            "finalized_at",
            "created_at",
            "updated_at",
        )

    def get_party_name(self, obj) -> str | None:
        if obj.party is None:
            return None

        return obj.party.trade_name or obj.party.legal_name

    def get_stage_count(self, obj) -> int:
        prefetched_stages = getattr(
            obj,
            "_prefetched_objects_cache",
            {},
        ).get("stages")

        if prefetched_stages is not None:
            return len(prefetched_stages)

        return obj.stages.count()

    def get_is_current(self, obj) -> bool:
        return is_current_revision(obj)

    def get_is_editable(self, obj) -> bool:
        return (
            obj.status == BudgetSheetStatus.DRAFT
            and is_current_revision(obj)
        )

    def get_bdi_configured(self, obj) -> bool:
        return bdi_is_configured(obj)

    def validate(self, attrs):
        if (
            self.instance is not None
            and self.instance.status != BudgetSheetStatus.DRAFT
        ):
            raise serializers.ValidationError(
                {
                    "status": (
                        "Somente uma planilha em rascunho pode ser alterada. "
                        "Gere uma nova revisão para continuar."
                    )
                }
            )

        proposal = attrs.get(
            "proposal",
            self.instance.proposal if self.instance else None,
        )
        party = attrs.get(
            "party",
            self.instance.party if self.instance else None,
        )
        department = attrs.get(
            "department",
            self.instance.department if self.instance else None,
        )
        number = attrs.get(
            "number",
            self.instance.number if self.instance else "",
        )
        errors = {}

        if (
            self.instance is not None
            and "proposal" in attrs
            and attrs["proposal"] is not None
            and attrs["proposal"].pk != self.instance.proposal_id
        ):
            errors["proposal"] = (
                "A proposta não pode ser trocada após a criação da planilha."
            )

        if proposal is not None:
            if party is not None and party.pk != proposal.party_id:
                errors["party"] = (
                    "O cliente deve ser o mesmo da proposta selecionada."
                )

            if (
                department is not None
                and proposal.department_id is not None
                and department.pk != proposal.department_id
            ):
                errors["department"] = (
                    "O departamento deve ser o mesmo da proposta selecionada."
                )

            attrs["party"] = proposal.party

            if proposal.department_id is not None:
                attrs["department"] = proposal.department

        elif not str(number or "").strip():
            errors["number"] = (
                "Informe o número quando a planilha não estiver "
                "vinculada a uma proposta."
            )

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def create(self, validated_data):
        try:
            proposal = validated_data.get("proposal")
            with transaction.atomic():
                if proposal is not None:
                    # Serializa a alocação do próximo número de planilha para o
                    # mesmo PC. Revisão é outra dimensão e sempre começa em 00.
                    proposal.__class__.objects.select_for_update().get(pk=proposal.pk)
                    current_max = (
                        BudgetSheet.objects
                        .filter(
                            proposal=proposal,
                            revision=0,
                            revision_root__isnull=True,
                        )
                        .aggregate(value=Max("proposal_sequence"))["value"]
                    )
                    validated_data["proposal_sequence"] = (current_max + 1) if current_max is not None else 0
                    validated_data["revision"] = 0
                    # O número pertence à planilha independente, não ao payload do front.
                    # Preenche aqui também (além da proteção no model.save) para que a
                    # criação via API nunca dependa do cliente informar `number`.
                    validated_data["number"] = BudgetSheet.build_number(
                        proposal.code,
                        validated_data["proposal_sequence"],
                    )

                return super().create(validated_data)
        except DjangoValidationError as error:
            raise_api_validation_error(error)

    def update(self, instance, validated_data):
        try:
            return super().update(
                instance,
                validated_data,
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)


class BudgetCostConfigurationWriteSerializer(serializers.Serializer):
    bdi = serializers.JSONField(required=False)
    di = serializers.JSONField(required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(
                "Informe bdi e/ou di para salvar a configuração."
            )
        return attrs


class BudgetCostConfigurationReadSerializer(serializers.Serializer):
    budget_sheet_id = serializers.IntegerField(read_only=True)
    revision = serializers.IntegerField(read_only=True)
    bdi = serializers.JSONField(read_only=True)
    di = serializers.JSONField(read_only=True)


class BudgetBdiApplicationWriteSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=("ALL", "NONE"))


class GenerateBudgetSheetRevisionSerializer(
    serializers.Serializer
):
    reason = serializers.CharField(
        min_length=3,
        max_length=2000,
        trim_whitespace=True,
    )


class StageReorderSerializer(serializers.Serializer):
    stage_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )

    def validate_stage_ids(self, values):
        if len(values) != len(set(values)):
            raise serializers.ValidationError(
                "A lista não pode conter IDs repetidos."
            )
        return values


class ItemReorderSerializer(serializers.Serializer):
    item_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )

    def validate_item_ids(self, values):
        if len(values) != len(set(values)):
            raise serializers.ValidationError(
                "A lista não pode conter IDs repetidos."
            )
        return values



class BudgetSheetDiffItemSerializer(serializers.Serializer):
    stage_order = serializers.IntegerField(read_only=True)
    item_order = serializers.IntegerField(read_only=True)
    current_quantity = serializers.CharField(read_only=True)
    previous_quantity = serializers.CharField(
        read_only=True, allow_null=True
    )
    quantity_delta = serializers.CharField(
        read_only=True, allow_null=True
    )
    current_total = serializers.CharField(read_only=True)
    previous_total = serializers.CharField(
        read_only=True, allow_null=True
    )
    total_delta = serializers.CharField(
        read_only=True, allow_null=True
    )


class BudgetSheetDiffSerializer(serializers.Serializer):
    current_id = serializers.IntegerField(read_only=True)
    previous_id = serializers.IntegerField(read_only=True)
    previous_revision = serializers.IntegerField(read_only=True)
    total_delta = serializers.CharField(read_only=True)
    item_changes = BudgetSheetDiffItemSerializer(
        many=True, read_only=True
    )


class BudgetExportPreviewSerializer(serializers.Serializer):
    audience = serializers.ChoiceField(
        choices=("CLIENT", "DARUIX"), read_only=True
    )
    budget_sheet_id = serializers.IntegerField(read_only=True)
    number = serializers.CharField(read_only=True)
    revision = serializers.IntegerField(read_only=True)
    proposal_code = serializers.CharField(
        read_only=True, allow_null=True
    )
    party_name = serializers.CharField(
        read_only=True, allow_null=True
    )
    total_amount = serializers.CharField(read_only=True)
    # Estrutura hierárquica variável: etapa -> composição -> componentes.
    nodes = serializers.JSONField(read_only=True)


class BudgetSheetRevisionSerializer(
    serializers.ModelSerializer
):
    is_current = serializers.SerializerMethodField()
    is_editable = serializers.SerializerMethodField()

    class Meta:
        model = BudgetSheet
        fields = (
            "id",
            "number",
            "proposal_sequence",
            "revision",
            "status",
            "revision_reason",
            "previous_revision",
            "total_amount",
            "is_current",
            "is_editable",
            "finalized_at",
            "created_at",
        )
        read_only_fields = fields

    def get_is_current(self, obj) -> bool:
        # Neste endpoint, "current" significa a revisão atualmente aberta
        # pelo usuário (o id usado na rota), preservando o contrato existente.
        return obj.pk == self.context.get("current_budget_sheet_id")

    def get_is_editable(self, obj) -> bool:
        return (
            obj.status == BudgetSheetStatus.DRAFT
            and is_current_revision(obj)
        )

class SupplyTypeSerializer(serializers.Serializer):
    value = serializers.CharField(read_only=True)
    label = serializers.CharField(read_only=True)


class SupplyAutocompleteSerializer(serializers.ModelSerializer):
    unit_measure_name = serializers.CharField(
        source="unit_measure.nome",
        read_only=True,
        allow_null=True,
    )
    unit_measure_abbreviation = serializers.CharField(
        source="unit_measure.sigla",
        read_only=True,
        allow_null=True,
    )
    material_group_name = serializers.CharField(
        source="material_group.nome",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Supply
        fields = (
            "id",
            "origin",
            "description",
            "full_description",
            "specification",
            "supply_type",
            "unit",
            "unit_measure",
            "unit_measure_name",
            "unit_measure_abbreviation",
            "material_group",
            "material_group_name",
        )
