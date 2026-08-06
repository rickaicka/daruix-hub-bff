from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from budgeting.choices import CompositionStatus, DataOrigin
from budgeting.models import (
    ServiceComposition,
    ServiceCompositionItem,
    ServiceCompositionVersion,
)


MONEY_QUANTUM = Decimal("0.0001")


def _latest_version(
    composition: ServiceComposition,
    *,
    lock: bool = False,
) -> ServiceCompositionVersion | None:
    queryset = composition.versions.order_by("-number")
    if lock:
        queryset = queryset.select_for_update()
    return queryset.first()


def _subcomposition_unit(subcomposition: ServiceComposition) -> str:
    version = subcomposition.latest_version
    return version.unit if version else ""


def _create_items(
    version: ServiceCompositionVersion,
    items: list[dict[str, Any]],
) -> None:
    for default_position, raw_item_data in enumerate(items):
        item_data = dict(raw_item_data)
        supply = item_data.get("supply")
        subcomposition = item_data.get("subcomposition")

        description = item_data.pop("description_snapshot", "")
        unit = item_data.pop("unit_snapshot", "")
        position = item_data.pop("position", default_position)

        if supply is not None:
            description = description or supply.description
            unit = unit or supply.unit
        elif subcomposition is not None:
            description = description or subcomposition.name
            unit = unit or _subcomposition_unit(subcomposition)

        item = ServiceCompositionItem(
            version=version,
            position=position,
            description_snapshot=description,
            unit_snapshot=unit,
            **item_data,
        )
        item.full_clean()
        item.save()


def _recalculate(version: ServiceCompositionVersion) -> None:
    material = Decimal("0")
    labor = Decimal("0")
    equipment = Decimal("0")

    for item in version.items.all():
        material += item.coefficient * item.material_unit_price
        labor += item.coefficient * item.labor_unit_price
        equipment += item.coefficient * item.equipment_unit_price

    material = material.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    labor = labor.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    equipment = equipment.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)

    version.material_total = material
    version.labor_total = labor
    version.equipment_total = equipment
    version.total = material + labor + equipment
    version.save(
        update_fields=(
            "material_total",
            "labor_total",
            "equipment_total",
            "total",
            "updated_at",
        )
    )


@transaction.atomic
def create_composition(validated_data: dict[str, Any]) -> ServiceComposition:
    data = dict(validated_data)
    items = list(data.pop("items", []))
    unit = data.pop("unit", "")

    composition = ServiceComposition.objects.create(
        origin=DataOrigin.HUB,
        **data,
    )
    version = ServiceCompositionVersion.objects.create(
        composition=composition,
        number=1,
        status=CompositionStatus.DRAFT,
        origin=DataOrigin.HUB,
        unit=unit,
    )
    _create_items(version, items)
    _recalculate(version)
    return composition


@transaction.atomic
def update_draft(
    composition: ServiceComposition,
    validated_data: dict[str, Any],
) -> ServiceComposition:
    if composition.origin != DataOrigin.HUB:
        raise ValidationError("Composições legadas são imutáveis.")

    version = _latest_version(composition, lock=True)
    if version is None or not version.is_mutable:
        raise ValidationError(
            "Crie uma nova versão antes de alterar uma composição publicada."
        )

    data = dict(validated_data)
    items = data.pop("items", None)
    unit = data.pop("unit", None)

    if unit is not None and unit != version.unit:
        version.unit = unit
        version.save(update_fields=("unit", "updated_at"))

    changed_fields: list[str] = []
    for field_name, value in data.items():
        if getattr(composition, field_name) != value:
            setattr(composition, field_name, value)
            changed_fields.append(field_name)

    if changed_fields:
        composition.save(update_fields=(*changed_fields, "updated_at"))

    if items is not None:
        version.items.all().delete()
        _create_items(version, list(items))
        _recalculate(version)

    return composition


@transaction.atomic
def publish(composition: ServiceComposition) -> ServiceCompositionVersion:
    if composition.origin != DataOrigin.HUB:
        raise ValidationError("Composições legadas não podem ser publicadas.")

    version = _latest_version(composition, lock=True)
    if version is None or not version.is_mutable:
        raise ValidationError("Não existe um rascunho HUB para publicar.")
    if not version.items.exists():
        raise ValidationError("A composição precisa possuir ao menos um item.")

    _recalculate(version)
    version.status = CompositionStatus.PUBLISHED
    version.published_at = timezone.now()
    version.save(update_fields=("status", "published_at", "updated_at"))
    return version


@transaction.atomic
def new_version(composition: ServiceComposition) -> ServiceCompositionVersion:
    locked_composition = ServiceComposition.objects.select_for_update().get(
        pk=composition.pk
    )
    if locked_composition.origin != DataOrigin.HUB:
        raise ValidationError(
            "Copie a composição legada para o Hub antes de revisá-la."
        )

    source = _latest_version(locked_composition, lock=True)
    if source is None:
        raise ValidationError("A composição não possui uma versão para copiar.")
    if source.status == CompositionStatus.DRAFT:
        raise ValidationError("Já existe um rascunho para esta composição.")
    if source.status != CompositionStatus.PUBLISHED:
        raise ValidationError(
            "Somente uma versão publicada pode originar uma nova versão."
        )

    number = (
        locked_composition.versions.aggregate(value=Max("number"))["value"] or 0
    ) + 1
    target = ServiceCompositionVersion.objects.create(
        composition=locked_composition,
        number=number,
        status=CompositionStatus.DRAFT,
        origin=DataOrigin.HUB,
        unit=source.unit,
    )

    for source_item in source.items.select_related(
        "supply",
        "subcomposition",
    ):
        target_item = ServiceCompositionItem(
            version=target,
            item_type=source_item.item_type,
            supply=source_item.supply,
            subcomposition=source_item.subcomposition,
            description_snapshot=source_item.description_snapshot,
            unit_snapshot=source_item.unit_snapshot,
            coefficient=source_item.coefficient,
            material_unit_price=source_item.material_unit_price,
            labor_unit_price=source_item.labor_unit_price,
            equipment_unit_price=source_item.equipment_unit_price,
            position=source_item.position,
        )
        target_item.full_clean()
        target_item.save()

    _recalculate(target)
    return target
