"""Customize only the composition snapshot owned by a budget item."""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from budgeting.choices import BudgetSheetItemType, CompositionItemType
from budgeting.models import BudgetSheetStageItem
from budgeting.services.budget_sheets import (
    COEFFICIENT_18, ZERO, _flatten_composition_items, _get_locked_sheet,
    _latest_composition_version, _recalculate_composition_snapshot_costs,
    ensure_budget_sheet_editable, recalculate_budget_totals,
)


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root + ".")


def _coefficient(quantity: Decimal, parent_quantity: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 60
        value = (quantity / parent_quantity).quantize(COEFFICIENT_18, rounding=ROUND_HALF_UP)
    if value <= ZERO:
        raise ValidationError({"quantity": "A quantidade é pequena demais para esta composição."})
    return value


@transaction.atomic
def customize_budget_composition(item: BudgetSheetStageItem, data: dict[str, Any]) -> BudgetSheetStageItem:
    sheet = _get_locked_sheet(item.budget_sheet_stage.budget_sheet_id)
    ensure_budget_sheet_editable(sheet)
    locked = BudgetSheetStageItem.objects.select_for_update().get(
        pk=item.pk, budget_sheet_stage__budget_sheet=sheet,
    )
    if locked.item_type != BudgetSheetItemType.SERVICE_COMPOSITION:
        raise ValidationError({"item": "Somente uma composição possui componentes para personalizar."})
    if locked.composition_snapshot != data["expected_snapshot"] or locked.quantity != data["expected_quantity"]:
        raise ValidationError({"composition_snapshot": (
            "A composição foi alterada depois de abrir o editor. Recarregue a planilha e tente novamente."
        )})
    if locked.quantity <= ZERO:
        raise ValidationError({"quantity": "Informe uma quantidade maior que zero na composição."})

    snapshot = deepcopy(locked.composition_snapshot)
    components = snapshot.get("items")
    if not isinstance(components, list) or any(not isinstance(c, dict) for c in components):
        raise ValidationError({"composition_snapshot": "A composição não possui uma estrutura válida."})
    by_path = {c.get("source_path"): c for c in components}
    if len(by_path) != len(components) or any(not p for p in by_path):
        raise ValidationError({"composition_snapshot": "Os caminhos dos componentes são inválidos."})
    removed = data.get("removed_paths", [])
    if any(p not in by_path for p in removed):
        raise ValidationError({"removed_paths": "Um componente não pertence a esta composição."})
    updates = data.get("updates", [])
    if len({u["source_path"] for u in updates}) != len(updates):
        raise ValidationError({"updates": "Não repita o mesmo componente."})
    for update in updates:
        path = update["source_path"]
        target = by_path.get(path)
        if target is None or any(_under(path, root) for root in removed):
            raise ValidationError({"updates": "Um componente alterado não pertence à estrutura mantida."})
        if target.get("display_only") or target.get("item_type") == CompositionItemType.SUBCOMPOSITION:
            raise ValidationError({"updates": "Edite as quantidades e os custos nos itens da subcomposição."})
        if "quantity" in update:
            target["coefficient"] = str(_coefficient(update["quantity"], locked.quantity))
        for field in ("material_unit_price", "labor_unit_price", "equipment_unit_price"):
            if field in update:
                target[field] = str(update[field])
        target["customized"] = True

    # Keep surviving paths stable: enabled controls and provenance use these keys.
    components = [c for c in components if not any(_under(c["source_path"], p) for p in removed)]
    surviving = {c["source_path"]: c for c in components}
    next_positions: dict[str, int] = {}
    for path in by_path:
        parent, _, last = path.rpartition(".")
        next_positions[parent] = max(next_positions.get(parent, 0), int(last or path))

    for addition in data.get("additions", []):
        parent_path = addition.get("parent_path", "")
        if parent_path:
            parent = surviving.get(parent_path)
            if not parent or not parent.get("display_only"):
                raise ValidationError({"parent_path": "Escolha uma subcomposição mantida nesta planilha."})
            if parent.get("enabled", True) is False:
                raise ValidationError({"parent_path": "Reabilite a subcomposição antes de adicionar componentes."})
        next_positions[parent_path] = next_positions.get(parent_path, 0) + 1
        path = ".".join(filter(None, (parent_path, str(next_positions[parent_path]))))
        if len(path) > 120:
            raise ValidationError({"parent_path": "A hierarquia possui níveis demais."})
        coefficient = _coefficient(addition["quantity"], locked.quantity)
        supply = addition.get("supply")
        subcomposition = addition.get("subcomposition")
        component = {
            "source_path": path, "position": next_positions[parent_path] - 1,
            "item_type": addition["item_type"],
            "supply_id": supply.pk if supply else None,
            "subcomposition_id": subcomposition.pk if subcomposition else None,
            "description_snapshot": addition.get("description_snapshot", ""),
            "unit_snapshot": addition.get("unit_snapshot", ""),
            "coefficient": str(coefficient), "enabled": True,
            "display_only": bool(subcomposition), "customized": True,
            "material_unit_price": str(addition.get("material_unit_price", ZERO)),
            "labor_unit_price": str(addition.get("labor_unit_price", ZERO)),
            "equipment_unit_price": str(addition.get("equipment_unit_price", ZERO)),
            "subtotal": "0.00",
        }
        if supply:
            component["description_snapshot"] = component["description_snapshot"] or supply.description
            component["unit_snapshot"] = component["unit_snapshot"] or (
                supply.unit_measure.sigla if supply.unit_measure_id else supply.unit
            )
        if subcomposition:
            # Resolve once, then freeze every descendant; never write the catalog.
            version = _latest_composition_version(subcomposition)
            component["description_snapshot"] = subcomposition.name
            component["unit_snapshot"] = version.unit
            component["source_version_id"] = version.pk
            component["source_version_number"] = version.number
            leaves = _flatten_composition_items(
                version, prefix=tuple(int(p) for p in path.split(".")),
                multiplier=coefficient, visited=frozenset({locked.service_composition_id}),
            )
            if not leaves:
                raise ValidationError({"subcomposition": "A subcomposição selecionada não possui itens."})
            components.extend([component, *leaves])
        else:
            components.append(component)

    if not any(not c.get("display_only", False) for c in components):
        raise ValidationError({"components": "Mantenha pelo menos um componente na composição."})
    if not updates and not removed and not data.get("additions"):
        return locked

    snapshot["items"] = components
    snapshot["customized"] = True
    snapshot["customized_at"] = timezone.now().isoformat()
    snapshot, material, labor, equipment, total = _recalculate_composition_snapshot_costs(snapshot)
    # The persisted parent costs have four decimals; component costs retain eight.
    for value in (material, labor, equipment, total):
        if value >= Decimal("100000000000000"):
            raise ValidationError({"components": "O custo ultrapassa o limite permitido para a composição."})
    if total * locked.quantity >= Decimal("10000000000000000"):
        raise ValidationError({"components": "O total ultrapassa o limite permitido para a linha."})
    BudgetSheetStageItem.objects.filter(pk=locked.pk).update(
        composition_snapshot=snapshot, material_unit_cost=material,
        labor_unit_cost=labor, equipment_unit_cost=equipment, unit_cost=total,
        updated_at=timezone.now(),
    )
    # Existing pricing handles BDI/DI, discounts, stage totals and sheet totals.
    # Any failure rolls back the whole customization.
    recalculate_budget_totals(sheet.pk)
    locked.refresh_from_db()
    return locked
