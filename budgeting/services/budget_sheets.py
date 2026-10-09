from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Any, Iterable

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Max, Q
from django.utils import timezone

from budgeting.choices import (
    BudgetSheetItemType,
    BudgetSheetStatus,
    CompositionItemType,
    DataOrigin,
)
from budgeting.models import (
    BudgetSheet,
    BudgetSheetStage,
    BudgetSheetStageItem,
    ServiceComposition,
    ServiceCompositionVersion,
    Supply,
)

MONEY_2 = Decimal("0.01")
MONEY_4 = Decimal("0.0001")
QUANTITY_6 = Decimal("0.000001")
COEFFICIENT_18 = Decimal("0.000000000000000001")
ZERO = Decimal("0")


def money(value: Any) -> Decimal:
    return Decimal(value or 0).quantize(MONEY_2, rounding=ROUND_HALF_UP)


def money4(value: Any) -> Decimal:
    return Decimal(value or 0).quantize(MONEY_4, rounding=ROUND_HALF_UP)


def revision_group_query(budget_sheet: BudgetSheet) -> Q:
    root_id = budget_sheet.revision_root_id or budget_sheet.pk
    return Q(pk=root_id) | Q(revision_root_id=root_id)


def is_current_revision(budget_sheet: BudgetSheet) -> bool:
    root_id = budget_sheet.revision_root_id or budget_sheet.pk
    current_id = (
        BudgetSheet.objects
        .filter(Q(pk=root_id) | Q(revision_root_id=root_id))
        .order_by("-revision", "-id")
        .values_list("id", flat=True)
        .first()
    )
    return current_id == budget_sheet.pk


def ensure_budget_sheet_editable(budget_sheet: BudgetSheet) -> None:
    if budget_sheet.status != BudgetSheetStatus.DRAFT:
        raise ValidationError(
            {
                "status": (
                    "Somente uma planilha em rascunho pode ser alterada. "
                    "Gere uma nova revisão para continuar."
                )
            }
        )

    if not is_current_revision(budget_sheet):
        raise ValidationError(
            {
                "revision": (
                    "Somente a revisão mais recente pode ser alterada."
                )
            }
        )


def _get_locked_sheet(budget_sheet_id: int) -> BudgetSheet:
    # Não usar select_related aqui. Há FKs opcionais no modelo e PostgreSQL
    # pode rejeitar FOR UPDATE no lado anulável de OUTER JOIN.
    return BudgetSheet.objects.select_for_update().get(pk=budget_sheet_id)


def _latest_composition_version(
    composition: ServiceComposition,
) -> ServiceCompositionVersion:
    version = (
        composition.versions
        .order_by("-number", "-id")
        .first()
    )
    if version is None:
        raise ValidationError(
            {
                "service_composition": (
                    "A composição selecionada não possui versão disponível."
                )
            }
        )
    return version


def _flatten_composition_items(
    version: ServiceCompositionVersion,
    *,
    prefix: tuple[int, ...] = (),
    multiplier: Decimal = Decimal("1"),
    visited: frozenset[int] = frozenset(),
) -> list[dict[str, Any]]:
    """
    Congela a estrutura completa de uma composição.

    Mantém também as linhas de SUBCOMPOSITION no snapshot para que a
    hierarquia possa ser apresentada na planilha.

    Regras:
    - itens de subcomposição entram no snapshot com ``display_only=True``;
    - itens folha entram com ``display_only=False``;
    - todos os itens nascem com ``enabled=True`` para que a planilha
      possa decidir depois quais componentes participarão do orçamento.
    """

    if version.composition_id in visited:
        raise ValidationError(
            "Foi detectado um ciclo entre composições de serviço."
        )

    visited = visited | {version.composition_id}

    flattened: list[dict[str, Any]] = []

    components = (
        version.items.select_related(
            "supply",
            "subcomposition",
        ).order_by(
            "position",
            "id",
        )
    )

    for display_index, component in enumerate(
        components,
        start=1,
    ):
        path = (*prefix, display_index)

        source_path = ".".join(
            str(part)
            for part in path
        )

        own_coefficient = Decimal(
            component.coefficient or 0
        )

        effective_coefficient = (
            multiplier * own_coefficient
        )

        #
        # SUBCOMPOSIÇÃO
        #
        # A própria linha da subcomposição entra no snapshot
        # para que a árvore possa ser desenhada na planilha.
        # Seus filhos vêm logo em seguida.
        #
        if (
            component.item_type
            == CompositionItemType.SUBCOMPOSITION
            and component.subcomposition_id
        ):
            subversion = _latest_composition_version(
                component.subcomposition
            )

            material = money4(
                subversion.material_total
            )

            labor = money4(
                subversion.labor_total
            )

            equipment = money4(
                subversion.equipment_total
            )

            component_unit_cost = money4(
                material + labor + equipment
            )

            material_subtotal = money(
                effective_coefficient * material
            )

            labor_subtotal = money(
                effective_coefficient * labor
            )

            equipment_subtotal = money(
                effective_coefficient * equipment
            )

            flattened.append(
                {
                    "source_path": source_path,
                    "position": component.position,
                    "item_type": CompositionItemType.SUBCOMPOSITION,
                    "supply_id": None,
                    "subcomposition_id": component.subcomposition_id,
                    "description_snapshot": (
                        component.description_snapshot
                        or component.subcomposition.name
                    ),
                    "unit_snapshot": (
                        component.unit_snapshot
                        or subversion.unit
                        or ""
                    ),
                    "coefficient": str(
                        effective_coefficient
                    ),
                    "material_unit_price": str(material),
                    "labor_unit_price": str(labor),
                    "equipment_unit_price": str(equipment),
                    "unit_cost": str(
                        component_unit_cost
                    ),
                    "subtotal": str(
                        money(
                            material_subtotal
                            + labor_subtotal
                            + equipment_subtotal
                        )
                    ),
                    #
                    # Linha usada para visualização/hierarquia.
                    # O cálculo final da composição tratará esse
                    # item conforme a regra de display_only.
                    #
                    "display_only": True,
                    #
                    # Todos os componentes da composição entram
                    # habilitados por padrão na planilha.
                    #
                    "enabled": True,
                }
            )

            #
            # Depois da linha da composição, abre seus filhos.
            #
            flattened.extend(
                _flatten_composition_items(
                    subversion,
                    prefix=path,
                    multiplier=effective_coefficient,
                    visited=visited,
                )
            )

            continue

        #
        # FOLHAS
        #
        material = Decimal(component.material_unit_price)

        labor = Decimal(component.labor_unit_price)

        equipment = Decimal(component.equipment_unit_price)

        component_unit_cost = material + labor + equipment

        material_subtotal = money(
            effective_coefficient * material
        )

        labor_subtotal = money(
            effective_coefficient * labor
        )

        equipment_subtotal = money(
            effective_coefficient * equipment
        )

        flattened.append(
            {
                "source_path": source_path,
                "position": component.position,
                "item_type": component.item_type,
                "supply_id": component.supply_id,
                "subcomposition_id": component.subcomposition_id,
                "description_snapshot": component.description_snapshot,
                "unit_snapshot": component.unit_snapshot,
                "coefficient": str(
                    effective_coefficient
                ),
                "material_unit_price": str(material),
                "labor_unit_price": str(labor),
                "equipment_unit_price": str(equipment),
                "unit_cost": str(
                    component_unit_cost
                ),
                "subtotal": str(
                    money(
                        material_subtotal
                        + labor_subtotal
                        + equipment_subtotal
                    )
                ),
                "display_only": False,
                "enabled": True,
            }
        )

    return flattened


def build_composition_snapshot(
    composition: ServiceComposition,
) -> dict[str, Any]:
    version = _latest_composition_version(composition)
    return {
        "composition_id": composition.pk,
        "version_id": version.pk,
        "version_number": version.number,
        "code": composition.code,
        "name": composition.name,
        "unit": version.unit,
        "material_total": str(money4(version.material_total)),
        "labor_total": str(money4(version.labor_total)),
        "equipment_total": str(money4(version.equipment_total)),
        "total": str(money4(version.total)),
        "items": _flatten_composition_items(version),
    }


def apply_budget_item_reference_snapshot(
    item: BudgetSheetStageItem,
) -> None:
    """Atualiza snapshot somente quando a referência do item é escolhida/trocada."""
    if item.item_type == BudgetSheetItemType.SERVICE_COMPOSITION:
        if not item.service_composition_id:
            raise ValidationError(
                {"service_composition": "Selecione uma composição de serviço."}
            )

        composition = ServiceComposition.objects.get(
            pk=item.service_composition_id,
            is_active=True,
        )
        snapshot = build_composition_snapshot(composition)
        item.description_snapshot = composition.name
        item.unit_snapshot = snapshot["unit"] or ""
        item.composition_version_number = snapshot["version_number"]
        item.material_unit_cost = Decimal(snapshot["material_total"])
        item.labor_unit_cost = Decimal(snapshot["labor_total"])
        item.equipment_unit_cost = Decimal(snapshot["equipment_total"])
        item.unit_cost = Decimal(snapshot["total"])
        item.composition_snapshot = snapshot
        item.supply_id = None

    elif item.item_type == BudgetSheetItemType.SUPPLY:
        if not item.supply_id:
            raise ValidationError({"supply": "Selecione um insumo."})

        supply = (
            Supply.objects
            .select_related("unit_measure")
            .get(pk=item.supply_id, is_active=True)
        )
        item.description_snapshot = supply.description
        item.unit_snapshot = (
            supply.unit_measure.sigla
            if supply.unit_measure_id
            else supply.unit
        ) or ""
        item.service_composition_id = None
        item.composition_version_number = None
        item.composition_snapshot = {}

        # Supply ainda não possui uma fonte oficial de custo de compra.
        # Não fabricamos custo interno para o orçamento.
        item.material_unit_cost = ZERO
        item.labor_unit_cost = ZERO
        item.equipment_unit_cost = ZERO
        item.unit_cost = Decimal(item.unit_price or 0)

    elif item.item_type == BudgetSheetItemType.FREE_TEXT:
        item.service_composition_id = None
        item.supply_id = None
        item.composition_version_number = None
        item.composition_snapshot = {}
        item.material_unit_cost = ZERO
        item.labor_unit_cost = ZERO
        item.equipment_unit_cost = ZERO
        item.unit_cost = ZERO

        if not str(item.description_snapshot or "").strip():
            raise ValidationError(
                {"description_snapshot": "Informe a descrição do item livre."}
            )
    else:
        raise ValidationError({"item_type": "Tipo de item inválido."})

    if item.unit_cost and item.unit_cost > 0:
        item.pricing_factor = money4(
            Decimal(item.unit_price or 0) / item.unit_cost
        )
    else:
        item.pricing_factor = ZERO


def _recalculate_composition_snapshot_costs(
    snapshot: dict[str, Any],
) -> tuple[dict[str, Any], Decimal, Decimal, Decimal, Decimal]:
    """Keep unit costs precise; round money only at line display/final pricing."""
    with localcontext() as context:
        context.prec = 60
        return _calculate_snapshot_costs(snapshot)


def _calculate_snapshot_costs(snapshot: dict[str, Any]) -> tuple[dict[str, Any], Decimal, Decimal, Decimal, Decimal]:
    updated = deepcopy(snapshot)
    components = updated.get("items")
    if not isinstance(components, list):
        raise ValidationError({"composition_snapshot": "O snapshot da composição não possui itens válidos."})
    by_path = {}
    for component in components:
        if not isinstance(component, dict) or not component.get("source_path"):
            raise ValidationError({"composition_snapshot": "O snapshot possui um componente inválido."})
        path = str(component["source_path"])
        if path in by_path:
            raise ValidationError({"composition_snapshot": "O snapshot possui caminhos repetidos."})
        by_path[path] = component

    totals = [ZERO, ZERO, ZERO]
    groups = {path: [ZERO, ZERO, ZERO] for path, c in by_path.items() if c.get("display_only")}
    price_fields = ("material_unit_price", "labor_unit_price", "equipment_unit_price")
    for path, component in by_path.items():
        component.setdefault("enabled", True)
        if component.get("display_only"):
            continue
        coefficient = Decimal(str(component.get("coefficient") or 0))
        prices = [Decimal(str(component.get(field) or 0)) for field in price_fields]
        if coefficient < ZERO or any(price < ZERO or not price.is_finite() for price in prices) or not coefficient.is_finite():
            raise ValidationError({"composition_snapshot": "Quantidade e custos devem ser números não negativos."})
        component["unit_cost"] = str(sum(prices, ZERO))
        ancestors = [".".join(path.split(".")[:i]) for i in range(1, len(path.split(".")))]
        enabled = component["enabled"] and all(by_path.get(parent, {}).get("enabled", True) for parent in ancestors)
        amounts = [coefficient * price if enabled else ZERO for price in prices]
        component["subtotal"] = str(money(sum(amounts, ZERO)))
        for i, amount in enumerate(amounts):
            totals[i] += amount
            for parent in ancestors:
                if parent in groups:
                    groups[parent][i] += amount

    for path, amounts in groups.items():
        component = by_path[path]
        coefficient = Decimal(str(component.get("coefficient") or 0))
        total = sum(amounts, ZERO)
        component["subtotal"] = str(money(total))
        component["unit_cost"] = str((total / coefficient).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP) if coefficient > ZERO else ZERO)
        for field, amount in zip(price_fields, amounts):
            component[field] = str((amount / coefficient).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP) if coefficient > ZERO else ZERO)

    material, labor, equipment = (money4(amount) for amount in totals)
    # Quantize once after summing: do not round each component's unit subtotal
    # to cents before multiplying the budget item's quantity.
    total = money4(sum(totals, ZERO))
    for field, value in zip(("material_total", "labor_total", "equipment_total", "total"), (material, labor, equipment, total)):
        updated[field] = str(value)
    return updated, material, labor, equipment, total


@transaction.atomic
def update_composition_component_quantity(
    item: BudgetSheetStageItem,
    source_path: str,
    quantity: Decimal,
) -> BudgetSheetStageItem:
    sheet_id = (
        item
        .budget_sheet_stage
        .budget_sheet_id
    )

    locked_sheet = _get_locked_sheet(
        sheet_id
    )

    ensure_budget_sheet_editable(
        locked_sheet
    )

    locked_item = (
        BudgetSheetStageItem.objects
        .select_for_update()
        .select_related(
            "budget_sheet_stage"
        )
        .get(
            pk=item.pk,
            budget_sheet_stage__budget_sheet=(
                locked_sheet
            ),
        )
    )

    if (
        locked_item.item_type
        != BudgetSheetItemType
        .SERVICE_COMPOSITION
    ):
        raise ValidationError(
            {
                "item": (
                    "Somente componentes de "
                    "uma composição de serviço "
                    "possuem quantidade editável."
                )
            }
        )

    parent_quantity = Decimal(
        locked_item.quantity
        or 0
    )

    if parent_quantity <= ZERO:
        raise ValidationError(
            {
                "quantity": (
                    "Defina uma quantidade "
                    "maior que zero na composição "
                    "antes de editar seus "
                    "componentes."
                )
            }
        )

    requested_quantity = Decimal(
        quantity
    ).quantize(
        QUANTITY_6,
        rounding=ROUND_HALF_UP,
    )

    if requested_quantity <= ZERO:
        raise ValidationError(
            {
                "quantity": (
                    "A quantidade deve ser "
                    "maior que zero."
                )
            }
        )

    snapshot = deepcopy(
        locked_item.composition_snapshot
        or {}
    )

    components = snapshot.get(
        "items"
    )

    if not isinstance(
        components,
        list,
    ):
        raise ValidationError(
            {
                "composition_snapshot": (
                    "A composição não possui "
                    "um snapshot de componentes "
                    "válido."
                )
            }
        )

    normalized_source_path = str(
        source_path
    ).strip()

    if not normalized_source_path:
        raise ValidationError(
            {
                "source_path": (
                    "Informe o componente da "
                    "composição."
                )
            }
        )

    target = next(
        (
            component
            for component in components
            if (
                isinstance(
                    component,
                    dict,
                )
                and str(
                    component.get(
                        "source_path"
                    )
                    or ""
                ).strip()
                == normalized_source_path
            )
        ),
        None,
    )

    if target is None:
        raise ValidationError(
            {
                "source_path": (
                    "O componente informado "
                    "não pertence ao snapshot "
                    "desta composição."
                )
            }
        )

    if bool(
        target.get(
            "display_only",
            False,
        )
    ):
        raise ValidationError(
            {
                "component": (
                    "Esta linha representa uma "
                    "subcomposição e é apenas "
                    "visual na planilha. Altere "
                    "a quantidade pela linha pai "
                    "da composição."
                )
            }
        )

    if target.get(
        "enabled",
        True,
    ) is False:
        raise ValidationError(
            {
                "component": (
                    "Este componente está "
                    "desabilitado nesta planilha."
                )
            }
        )

    #
    # O input representa a quantidade efetiva do filho.
    #
    # Exemplo:
    #
    # pai = 3
    # filho = 6
    #
    # coeficiente interno = 6 / 3 = 2
    #
    # Mantemos o coeficiente no snapshot para que, caso
    # o pai depois vire 4, o filho passe automaticamente
    # para 8.
    #
    coefficient = (
        requested_quantity
        / parent_quantity
    ).quantize(
        COEFFICIENT_18,
        rounding=ROUND_HALF_UP,
    )

    if coefficient <= ZERO:
        raise ValidationError(
            {
                "quantity": (
                    "A quantidade informada "
                    "é pequena demais para "
                    "a quantidade atual "
                    "da composição."
                )
            }
        )

    target["coefficient"] = str(
        coefficient
    )

    target["enabled"] = True

    (
        snapshot,
        material_total,
        labor_total,
        equipment_total,
        total,
    ) = (
        _recalculate_composition_snapshot_costs(
            snapshot
        )
    )

    BudgetSheetStageItem.objects.filter(
        pk=locked_item.pk,
    ).update(
        composition_snapshot=snapshot,
        material_unit_cost=(
            material_total
        ),
        labor_unit_cost=(
            labor_total
        ),
        equipment_unit_cost=(
            equipment_total
        ),
        unit_cost=total,
        updated_at=timezone.now(),
    )

    #
    # A alteração do filho altera o custo
    # unitário do pai.
    #
    # O recálculo abaixo atualiza:
    #
    # - BDI;
    # - unit_price do pai;
    # - subtotal do pai;
    # - subtotal da etapa;
    # - total geral da planilha.
    #
    recalculate_budget_totals(
        locked_sheet.pk
    )

    locked_item.refresh_from_db()

    return locked_item

@transaction.atomic
def update_composition_component_enabled(
    item: BudgetSheetStageItem,
    source_path: str,
    enabled: bool,
) -> BudgetSheetStageItem:
    sheet_id = (
        item
        .budget_sheet_stage
        .budget_sheet_id
    )

    locked_sheet = _get_locked_sheet(
        sheet_id
    )

    ensure_budget_sheet_editable(
        locked_sheet
    )

    locked_item = (
        BudgetSheetStageItem.objects
        .select_for_update()
        .select_related(
            "budget_sheet_stage"
        )
        .get(
            pk=item.pk,
            budget_sheet_stage__budget_sheet=(
                locked_sheet
            ),
        )
    )

    if (
        locked_item.item_type
        != BudgetSheetItemType
        .SERVICE_COMPOSITION
    ):
        raise ValidationError(
            {
                "item": (
                    "Somente componentes de uma "
                    "composição de serviço podem "
                    "ser habilitados ou "
                    "desabilitados."
                )
            }
        )

    snapshot = deepcopy(
        locked_item.composition_snapshot
        or {}
    )

    components = snapshot.get(
        "items"
    )

    if not isinstance(
        components,
        list,
    ):
        raise ValidationError(
            {
                "composition_snapshot": (
                    "A composição não possui "
                    "um snapshot de componentes "
                    "válido."
                )
            }
        )

    normalized_source_path = str(
        source_path
    ).strip()

    if not normalized_source_path:
        raise ValidationError(
            {
                "source_path": (
                    "Informe o componente da "
                    "composição."
                )
            }
        )

    target = None

    components_by_path: dict[
        str,
        dict[str, Any],
    ] = {}

    for component in components:
        if not isinstance(
            component,
            dict,
        ):
            raise ValidationError(
                {
                    "composition_snapshot": (
                        "O snapshot da composição "
                        "possui um componente "
                        "inválido."
                    )
                }
            )

        current_path = str(
            component.get(
                "source_path"
            )
            or ""
        ).strip()

        if not current_path:
            continue

        #
        # Compatibilidade com snapshots antigos:
        # se não existir enabled, o item é
        # considerado habilitado.
        #
        component["enabled"] = bool(
            component.get(
                "enabled",
                True,
            )
        )

        components_by_path[
            current_path
        ] = component

        if (
            current_path
            == normalized_source_path
        ):
            target = component

    if target is None:
        raise ValidationError(
            {
                "source_path": (
                    "O componente informado "
                    "não pertence ao snapshot "
                    "desta composição."
                )
            }
        )

    normalized_enabled = bool(
        enabled
    )

    target_prefix = (
        normalized_source_path
        + "."
    )

    #
    # Se o usuário desabilitar uma composição
    # intermediária, toda a subárvore também
    # precisa ser desabilitada.
    #
    # Exemplo:
    #
    # 1       Fundação
    # 1.1     Concreto
    # 1.2     Aço
    #
    # Desabilitar "1" desabilita "1.1" e "1.2".
    #
    if not normalized_enabled:
        for current_path, component in (
            components_by_path.items()
        ):
            if (
                current_path
                == normalized_source_path
                or current_path.startswith(
                    target_prefix
                )
            ):
                component["enabled"] = False

    else:
        #
        # Reabilitando:
        #
        # - se for uma subcomposição/agrupador,
        #   reabilita a subárvore inteira;
        # - se for uma folha, reabilita só a
        #   folha e seus ancestrais visuais.
        #
        target_is_group = bool(
            target.get(
                "display_only",
                False,
            )
        )

        if target_is_group:
            for current_path, component in (
                components_by_path.items()
            ):
                if (
                    current_path
                    == normalized_source_path
                    or current_path.startswith(
                        target_prefix
                    )
                ):
                    component["enabled"] = True

        else:
            target["enabled"] = True

        #
        # Ao reabilitar uma folha, seus pais
        # precisam voltar como enabled=True
        # para a árvore não ficar inconsistente.
        #
        # Exemplo:
        #
        # 1       Fundação
        # 1.1     Concreto
        #
        # Reabilitar "1.1" reabilita também "1".
        #
        path_parts = (
            normalized_source_path
            .split(".")
        )

        for index in range(
            1,
            len(path_parts),
        ):
            ancestor_path = ".".join(
                path_parts[:index]
            )

            ancestor = components_by_path.get(
                ancestor_path
            )

            if ancestor is not None:
                ancestor["enabled"] = True

    (
        snapshot,
        material_total,
        labor_total,
        equipment_total,
        total,
    ) = (
        _recalculate_composition_snapshot_costs(
            snapshot
        )
    )

    BudgetSheetStageItem.objects.filter(
        pk=locked_item.pk,
    ).update(
        composition_snapshot=snapshot,
        material_unit_cost=(
            material_total
        ),
        labor_unit_cost=(
            labor_total
        ),
        equipment_unit_cost=(
            equipment_total
        ),
        unit_cost=total,
        updated_at=timezone.now(),
    )

    #
    # A alteração de enabled altera o custo
    # unitário da composição pai.
    #
    # O recálculo atualiza:
    #
    # - BDI;
    # - unit_price do pai;
    # - subtotal do pai;
    # - subtotal da etapa;
    # - total geral da planilha.
    #
    recalculate_budget_totals(
        locked_sheet.pk
    )

    locked_item.refresh_from_db()

    return locked_item

@transaction.atomic
def recalculate_budget_totals(
    budget_sheet_id: int,
) -> BudgetSheet:
    budget_sheet = _get_locked_sheet(budget_sheet_id)
    # Totais fazem parte do snapshot da revisão. Nunca permita uma chamada de
    # recálculo alterar uma revisão já finalizada ou histórica.
    ensure_budget_sheet_editable(budget_sheet)

    stages = list(
        BudgetSheetStage.objects
        .select_for_update()
        .filter(budget_sheet=budget_sheet)
        .order_by("order", "id")
    )

    total_amount = ZERO
    bdi_configured = bool((budget_sheet.bdi_configuration or {}).get("configured"))

    # O BDI efetivo depende do custo direto atual (A) e da memória D.I. (B).
    # Recalcule o cache antes de aplicar o multiplicador às composições.
    from budgeting.services.budget_costs import refresh_budget_sheet_bdi

    refresh_budget_sheet_bdi(budget_sheet)
    if bdi_configured:
        bdi_multiplier = Decimal(
            (budget_sheet.bdi_configuration or {}).get(
                "calculated_factor",
                "1",
            )
        )
    else:
        bdi_multiplier = Decimal("1")

    for stage in stages:
        stage_total = ZERO
        items = list(
            BudgetSheetStageItem.objects
            .select_for_update()
            .filter(budget_sheet_stage=stage)
            .order_by("order", "id")
        )

        for item in items:
            # A planilha de referência usa duas regras distintas:
            # - sem BDI: custo unitário completo x quantidade, arredondando só
            #   o total da linha para centavos;
            # - com BDI: primeiro ARRED(custo x fator; 2), formando o preço de
            #   venda unitário em centavos, e só então multiplica a quantidade.
            # O desconto unitário é aplicado após esse arredondamento do BDI.
            if item.item_type in (
                BudgetSheetItemType.SERVICE_COMPOSITION,
                BudgetSheetItemType.SUPPLY,
            ):
                base_unit_price = Decimal(item.unit_cost or 0)
                if item.apply_bdi and not bdi_configured:
                    raise ValidationError(
                        {
                            f"item_{item.pk}_apply_bdi": (
                                "A composição está marcada para receber BDI, mas "
                                "esta revisão ainda não possui memória BDI configurada."
                            )
                        }
                    )
                gross_unit_price = (
                    money(base_unit_price * bdi_multiplier)
                    if item.apply_bdi
                    else base_unit_price
                )
            else:
                gross_unit_price = Decimal(item.unit_price or 0)

            discount = Decimal(item.unit_discount or 0)
            if item.item_type == BudgetSheetItemType.FREE_TEXT and discount:
                raise ValidationError(
                    {"unit_discount": "Desconto disponível para insumos e composições."}
                )

            from budgeting.services.budget_pricing import discounted_unit_price

            precise_unit_price = discounted_unit_price(
                gross_unit_price,
                discount,
            )
            expected_unit_price = money4(precise_unit_price)
            expected_subtotal = money(
                Decimal(item.quantity or 0)
                * precise_unit_price
            )
            expected_factor = (
                money4(precise_unit_price / item.unit_cost)
                if item.unit_cost and item.unit_cost > 0
                else ZERO
            )

            updates: dict[str, Any] = {}
            if item.unit_price != expected_unit_price:
                updates["unit_price"] = expected_unit_price
                item.unit_price = expected_unit_price
            if item.subtotal != expected_subtotal:
                updates["subtotal"] = expected_subtotal
                item.subtotal = expected_subtotal
            if item.pricing_factor != expected_factor:
                updates["pricing_factor"] = expected_factor
                item.pricing_factor = expected_factor

            if updates:
                updates["updated_at"] = timezone.now()
                BudgetSheetStageItem.objects.filter(pk=item.pk).update(
                    **updates
                )

            stage_total += expected_subtotal

        stage_total = money(stage_total)
        if stage.subtotal != stage_total:
            BudgetSheetStage.objects.filter(pk=stage.pk).update(
                subtotal=stage_total,
                updated_at=timezone.now(),
            )
            stage.subtotal = stage_total

        total_amount += stage_total

    total_amount = money(total_amount)
    if budget_sheet.total_amount != total_amount:
        BudgetSheet.objects.filter(pk=budget_sheet.pk).update(
            total_amount=total_amount,
            updated_at=timezone.now(),
        )
        budget_sheet.total_amount = total_amount

    return budget_sheet


def next_stage_item_order(
    budget_sheet_stage: BudgetSheetStage,
) -> int:
    last_order = (
        budget_sheet_stage.items.aggregate(max_order=Max("order"))[
            "max_order"
        ]
        or 0
    )
    return last_order + 1


@transaction.atomic
def delete_stage_item(item: BudgetSheetStageItem) -> None:
    sheet_id = item.budget_sheet_stage.budget_sheet_id
    locked_sheet = _get_locked_sheet(sheet_id)
    ensure_budget_sheet_editable(locked_sheet)

    locked_item = (
        BudgetSheetStageItem.objects
        .select_for_update()
        .select_related("budget_sheet_stage")
        .get(
            pk=item.pk,
            budget_sheet_stage__budget_sheet=locked_sheet,
        )
    )
    stage = locked_item.budget_sheet_stage
    removed_order = locked_item.order
    locked_item.delete()

    following_items = list(
        BudgetSheetStageItem.objects
        .select_for_update()
        .filter(
            budget_sheet_stage=stage,
            order__gt=removed_order,
        )
        .order_by("order", "id")
    )

    # Atualiza um item por vez, do menor order para o maior.
    # Isso evita colisao temporaria com a constraint unica
    # (budget_sheet_stage, order) do PostgreSQL.
    for following_item in following_items:
        following_item.order -= 1
        following_item.save(update_fields=("order",))

    recalculate_budget_totals(locked_sheet.pk)


@transaction.atomic
def reorder_stage_items(
    budget_sheet_stage: BudgetSheetStage,
    item_ids: Iterable[int],
) -> list[BudgetSheetStageItem]:
    locked_sheet = _get_locked_sheet(
        budget_sheet_stage.budget_sheet_id
    )
    ensure_budget_sheet_editable(locked_sheet)
    locked_stage = (
        BudgetSheetStage.objects
        .select_for_update()
        .get(
            pk=budget_sheet_stage.pk,
            budget_sheet=locked_sheet,
        )
    )
    requested_ids = list(item_ids)

    if len(requested_ids) != len(set(requested_ids)):
        raise ValidationError(
            {"item_ids": "A lista não pode conter IDs repetidos."}
        )

    items = list(
        BudgetSheetStageItem.objects
        .select_for_update()
        .filter(budget_sheet_stage=locked_stage)
    )
    existing_ids = {item.pk for item in items}

    if set(requested_ids) != existing_ids:
        raise ValidationError(
            {
                "item_ids": (
                    "A lista deve conter exatamente todos os itens desta etapa."
                )
            }
        )

    BudgetSheetStageItem.objects.filter(
        budget_sheet_stage=locked_stage
    ).update(order=F("order") + 1_000_000)

    items_by_id = {item.pk: item for item in items}
    ordered_items = []
    for order, item_id in enumerate(requested_ids, start=1):
        reordered_item = items_by_id[item_id]
        reordered_item.order = order
        ordered_items.append(reordered_item)

    BudgetSheetStageItem.objects.bulk_update(
        ordered_items,
        fields=("order",),
    )

    return list(
        BudgetSheetStageItem.objects
        .filter(budget_sheet_stage=locked_stage)
        .select_related("service_composition", "supply")
        .order_by("order", "id")
    )


def build_unlinked_revision_number(
    root_number: str,
    root_revision: int,
    revision: int,
) -> str:
    normalized_number = str(root_number or "").strip()
    root_suffix = f"-{root_revision:02d}"
    if normalized_number.endswith(root_suffix):
        normalized_number = normalized_number[:-len(root_suffix)]
    return f"{normalized_number}-{revision:02d}"


def _validate_finalize(budget_sheet: BudgetSheet) -> None:
    stages = list(
        BudgetSheetStage.objects
        .filter(budget_sheet=budget_sheet)
        .prefetch_related("items")
        .order_by("order", "id")
    )
    errors: dict[str, Any] = {}

    if not stages:
        errors["stages"] = "Adicione ao menos uma etapa antes de finalizar."

    expected_stage_orders = list(range(1, len(stages) + 1))
    actual_stage_orders = [stage.order for stage in stages]
    if actual_stage_orders != expected_stage_orders:
        errors["stage_order"] = (
            "A ordem das etapas está inconsistente. Reordene antes de finalizar."
        )

    for stage in stages:
        items = list(stage.items.all().order_by("order", "id"))
        if not items:
            errors[f"stage_{stage.pk}"] = (
                f"A etapa {stage.order} não possui itens."
            )
            continue

        expected_item_orders = list(range(1, len(items) + 1))
        actual_item_orders = [item.order for item in items]
        if actual_item_orders != expected_item_orders:
            errors[f"stage_{stage.pk}_order"] = (
                f"A ordem dos itens da etapa {stage.order} está inconsistente."
            )

        for item in items:
            if Decimal(item.quantity or 0) <= 0:
                errors[f"item_{item.pk}_quantity"] = (
                    "A quantidade deve ser maior que zero."
                )
            if Decimal(item.unit_price or 0) < 0:
                errors[f"item_{item.pk}_unit_price"] = (
                    "O valor unitário não pode ser negativo."
                )
            if not str(item.description_snapshot or "").strip():
                errors[f"item_{item.pk}_description"] = (
                    "O item deve possuir descrição."
                )
            if (
                item.item_type == BudgetSheetItemType.SERVICE_COMPOSITION
                and not item.composition_snapshot
            ):
                errors[f"item_{item.pk}_snapshot"] = (
                    "A composição não possui snapshot interno. "
                    "Abra e salve novamente o item antes de finalizar."
                )
            if (
                item.item_type in (BudgetSheetItemType.SERVICE_COMPOSITION, BudgetSheetItemType.SUPPLY)
                and item.apply_bdi
                and not bool((budget_sheet.bdi_configuration or {}).get("configured"))
            ):
                errors[f"item_{item.pk}_apply_bdi"] = (
                    "Configure a memória BDI desta revisão antes de finalizar."
                )

    if errors:
        raise ValidationError(errors)


@transaction.atomic
def set_budget_sheet_bdi_application(
    budget_sheet_id: int,
    *,
    apply_bdi: bool,
) -> BudgetSheet:
    """Aplica/remove BDI em todas as composições da revisão atual.

    A memória BDI continua pertencendo à revisão. Esta operação altera apenas
    o sinalizador ``apply_bdi`` das linhas-pai SERVICE_COMPOSITION e recalcula
    o agregado uma única vez. Insumos e itens livres nunca recebem BDI.
    """
    budget_sheet = _get_locked_sheet(budget_sheet_id)
    ensure_budget_sheet_editable(budget_sheet)

    if apply_bdi and not bool(
        (budget_sheet.bdi_configuration or {}).get("configured")
    ):
        raise ValidationError(
            {
                "mode": (
                    "Configure e salve a memória BDI desta revisão antes de "
                    "aplicar o BDI em todas as composições."
                )
            }
        )

    now = timezone.now()
    (
        BudgetSheetStageItem.objects
        .filter(
            budget_sheet_stage__budget_sheet=budget_sheet,
            item_type__in=[BudgetSheetItemType.SERVICE_COMPOSITION, BudgetSheetItemType.SUPPLY],
        )
        .exclude(apply_bdi=apply_bdi)
        .update(
            apply_bdi=apply_bdi,
            updated_at=now,
        )
    )

    # Uma única recomposição dos preços/totais, independentemente da
    # quantidade de composições da planilha.
    return recalculate_budget_totals(budget_sheet.pk)


@transaction.atomic
def finalize_budget_sheet(
    budget_sheet_id: int,
    *,
    user=None,
) -> BudgetSheet:
    budget_sheet = _get_locked_sheet(budget_sheet_id)
    ensure_budget_sheet_editable(budget_sheet)

    recalculate_budget_totals(budget_sheet.pk)
    budget_sheet.refresh_from_db()
    _validate_finalize(budget_sheet)

    actor = user if getattr(user, "pk", None) else None
    budget_sheet.status = BudgetSheetStatus.FINALIZED
    budget_sheet.finalized_at = timezone.now()
    budget_sheet.finalized_by = actor
    budget_sheet.updated_by = actor
    budget_sheet.save(
        update_fields=(
            "status",
            "finalized_at",
            "finalized_by",
            "updated_by",
            "updated_at",
        )
    )
    return budget_sheet


@transaction.atomic
def generate_budget_revision(
    budget_sheet_id: int,
    *,
    reason: str,
    user=None,
) -> BudgetSheet:
    reason = str(reason or "").strip()
    if len(reason) < 3:
        raise ValidationError(
            {"reason": "Informe o motivo da revisão com ao menos 3 caracteres."}
        )

    source = _get_locked_sheet(budget_sheet_id)
    if source.status != BudgetSheetStatus.FINALIZED:
        raise ValidationError(
            {
                "status": (
                    "Apenas uma revisão finalizada pode originar uma nova revisão."
                )
            }
        )

    group = list(
        BudgetSheet.objects
        .select_for_update()
        .filter(revision_group_query(source))
        .order_by("revision", "id")
    )
    latest = group[-1]
    if latest.pk != source.pk:
        raise ValidationError(
            {
                "revision": (
                    "A nova revisão deve ser gerada a partir da revisão mais recente."
                )
            }
        )

    next_revision = source.revision + 1
    root = source.revision_root or source
    actor = user if getattr(user, "pk", None) else None

    number = ""
    if source.proposal_id is None:
        number = build_unlinked_revision_number(
            root.number,
            root.revision,
            next_revision,
        )

    target = BudgetSheet.objects.create(
        revision_root=root,
        previous_revision=source,
        revision_reason=reason,
        proposal_id=source.proposal_id,
        party_id=source.party_id,
        department_id=source.department_id,
        number=number,
        proposal_sequence=source.proposal_sequence,
        revision=next_revision,
        reference_date=source.reference_date,
        considerations=source.considerations,
        bdi_percentage=source.bdi_percentage,
        bdi_configuration=deepcopy(source.bdi_configuration),
        di_configuration=deepcopy(source.di_configuration),
        status=BudgetSheetStatus.DRAFT,
        total_amount=source.total_amount,
        created_by=actor,
        updated_by=actor,
    )

    source_stages = (
        BudgetSheetStage.objects
        .filter(budget_sheet=source)
        .select_related("stage")
        .prefetch_related("items")
        .order_by("order", "id")
    )

    for source_stage in source_stages:
        target_stage = BudgetSheetStage.objects.create(
            budget_sheet=target,
            stage_id=source_stage.stage_id,
            order=source_stage.order,
            name_snapshot=source_stage.name_snapshot,
            notes=source_stage.notes,
            subtotal=source_stage.subtotal,
        )

        for item in source_stage.items.all().order_by("order", "id"):
            cloned_item = BudgetSheetStageItem(
                budget_sheet_stage=target_stage,
                item_type=item.item_type,
                service_composition_id=item.service_composition_id,
                supply_id=item.supply_id,
                description_snapshot=item.description_snapshot,
                unit_snapshot=item.unit_snapshot,
                composition_version_number=item.composition_version_number,
                material_unit_cost=item.material_unit_cost,
                labor_unit_cost=item.labor_unit_cost,
                equipment_unit_cost=item.equipment_unit_cost,
                unit_cost=item.unit_cost,
                pricing_factor=item.pricing_factor,
                apply_bdi=item.apply_bdi,
                unit_discount=item.unit_discount,
                composition_snapshot=item.composition_snapshot,
                quantity=item.quantity,
                unit_price=item.unit_price,
                subtotal=item.subtotal,
                order=item.order,
                notes=item.notes,
                origin=DataOrigin.HUB,
            )
            cloned_item.save(preserve_financial_snapshot=True)

    # A nova revisão nasce como snapshot literal da revisão finalizada.
    # Não recalcule aqui: o BDI depende de A (custo direto) + D.I. e uma
    # recomposição durante a clonagem pode alterar retroativamente os valores
    # copiados caso a memória histórica seja de uma versão anterior da regra.
    # O primeiro recálculo da nova revisão acontece quando ela for efetivamente
    # editada (itens, quantidades, BDI/D.I.) ou finalizada.
    target.refresh_from_db()
    return target


def build_revision_diff(budget_sheet: BudgetSheet) -> dict[str, Any]:
    if not budget_sheet.previous_revision_id:
        return {
            "current_id": budget_sheet.pk,
            "previous_id": 0,
            "previous_revision": 0,
            "total_delta": "0.00",
            "item_changes": [],
        }

    previous = BudgetSheet.objects.get(pk=budget_sheet.previous_revision_id)
    previous_items = {
        (stage.order, item.order): item
        for stage in (
            BudgetSheetStage.objects
            .filter(budget_sheet=previous)
            .prefetch_related("items")
        )
        for item in stage.items.all()
    }

    changes: list[dict[str, Any]] = []
    stages = (
        BudgetSheetStage.objects
        .filter(budget_sheet=budget_sheet)
        .prefetch_related("items")
        .order_by("order", "id")
    )
    for stage in stages:
        for item in stage.items.all().order_by("order", "id"):
            old = previous_items.get((stage.order, item.order))
            old_qty = Decimal(old.quantity) if old else None
            old_total = Decimal(old.subtotal) if old else None
            changes.append(
                {
                    "stage_order": stage.order,
                    "item_order": item.order,
                    "current_quantity": str(item.quantity),
                    "previous_quantity": (
                        str(old_qty) if old_qty is not None else None
                    ),
                    "quantity_delta": (
                        str(Decimal(item.quantity) - old_qty)
                        if old_qty is not None
                        else None
                    ),
                    "current_total": str(item.subtotal),
                    "previous_total": (
                        str(old_total) if old_total is not None else None
                    ),
                    "total_delta": (
                        str(Decimal(item.subtotal) - old_total)
                        if old_total is not None
                        else None
                    ),
                }
            )

    return {
        "current_id": budget_sheet.pk,
        "previous_id": previous.pk,
        "previous_revision": previous.revision,
        "total_delta": str(
            money(
                Decimal(budget_sheet.total_amount)
                - Decimal(previous.total_amount)
            )
        ),
        "item_changes": changes,
    }
