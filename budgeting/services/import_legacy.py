from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone

from budgeting.choices import (
    BudgetStageLegacySource,
    CompositionItemType,
    CompositionStatus,
    DataOrigin,
    SupplyType,
)
from budgeting.models import (
    BudgetStageCatalog,
    MaterialGroup,
    ServiceComposition,
    ServiceCompositionItem,
    ServiceCompositionVersion,
    Supply,
    UnitMeasure,
)

from .legacy_bridge import LegacyBudgetingClient


def _key(value: Any) -> str:
    """Normaliza nomes de colunas sem alterar os valores vindos do legado."""
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(
        character for character in normalized if not unicodedata.combining(character)
    ).casefold()


def _value(row: dict[str, Any], *names: str, default: Any = None) -> Any:
    values_by_key = {_key(name): value for name, value in row.items()}
    for name in names:
        normalized_name = _key(name)
        if normalized_name in values_by_key:
            return values_by_key[normalized_name]
    return default


def _text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _reference_name_key(value: Any) -> str:
    normalized = _key(_text(value))
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    return " ".join(normalized.split())


GROUP_NAME_ALIASES = {
    "diversos": "Diversos",
    "epi s": "EPIs",
    "mterial basico": "Material Básico",
    "pintura": "Pintura",
}

LEGACY_SUPPLY_TYPE_MAP = {
    0: SupplyType.MATERIAL,
    1: SupplyType.SERVICE,
    # Existe somente um registro com valor 11:
    # "Chapisco em teto...". Pelo conteúdo, trata-se
    # de serviço e aparentemente é uma inconsistência
    # histórica do Access.
    11: SupplyType.SERVICE,
}


def _canonical_group_name(value: Any) -> str:
    original_name = _text(value)
    normalized_name = _reference_name_key(original_name)

    return GROUP_NAME_ALIASES.get(
        normalized_name,
        original_name,
    )


def _integer(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")

    normalized = (
        str(value).strip().replace("R$", "").replace("\u00a0", "").replace(" ", "")
    )
    if "," in normalized and "." in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    elif "," in normalized:
        normalized = normalized.replace(",", ".")

    try:
        return Decimal(normalized)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _hash(row: dict[str, Any]) -> str:
    serialized = json.dumps(
        row,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _supply_type(value: Any) -> str:
    numeric_value = _integer(value)

    if numeric_value is not None:
        return LEGACY_SUPPLY_TYPE_MAP.get(
            numeric_value,
            SupplyType.OTHER,
        )

    normalized = _key(value)

    if "material" in normalized or "insumo" in normalized:
        return SupplyType.MATERIAL

    if "servico" in normalized:
        return SupplyType.SERVICE

    if "mao" in normalized or "mdo" in normalized:
        return SupplyType.LABOR

    if "equip" in normalized:
        return SupplyType.EQUIPMENT

    return SupplyType.OTHER


def _has_changes(instance: Any, values: dict[str, Any]) -> bool:
    return any(
        getattr(instance, field_name) != value for field_name, value in values.items()
    )


def _apply_changes(instance: Any, values: dict[str, Any]) -> None:
    for field_name, value in values.items():
        setattr(instance, field_name, value)
    instance.imported_at = timezone.now()
    instance.save(update_fields=(*values.keys(), "imported_at", "updated_at"))


@dataclass
class ImportCounters:
    read: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    deactivated: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "read": self.read,
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "skipped": self.skipped,
            "deactivated": self.deactivated,
            "errors": len(self.errors),
        }


class LegacyCatalogImporter:
    SUPPLY_TABLE = "tblInsumos"
    COMPOSITION_TABLE = "tblComposicaoDeServico"
    COMPOSITION_ITEM_TABLE = "tblItemDaComposicaoDeServico"
    UNIT_MEASURE_TABLE = "tblUnidadeDeMedida"
    MATERIAL_GROUP_TABLE = "tblGrupoDeMaterial"

    def __init__(
        self,
        client: LegacyBudgetingClient | None = None,
        *,
        progress_callback: Callable[[str, ImportCounters], None] | None = None,
    ) -> None:
        self.client = client or LegacyBudgetingClient()
        self.progress_callback = progress_callback

    def _report_progress(self, resource: str, counters: ImportCounters) -> None:
        if self.progress_callback:
            self.progress_callback(resource, counters)

    def import_stage_catalog(
            self,
            *,
            dry_run: bool = False,
    ) -> ImportCounters:
        counters = ImportCounters()

        valid_sources = set(BudgetStageLegacySource.values)

        existing_by_identity = {
            (stage.legacy_source, stage.legacy_id): stage
            for stage in BudgetStageCatalog.objects.filter(
                origin=DataOrigin.LEGACY,
                legacy_id__isnull=False,
            )
        }

        imported_identities: set[tuple[str, int]] = set()
        imported_pks: set[int] = set()

        for row in self.client.list_stage_catalog():
            counters.read += 1
            self._report_progress(
                "stage-catalog",
                counters,
            )

            legacy_id = _integer(
                _value(
                    row,
                    "legacy_id",
                    "id",
                )
            )
            legacy_source = _text(
                _value(
                    row,
                    "legacy_source",
                    "source",
                )
            )
            legacy_key = _text(
                _value(
                    row,
                    "legacy_key",
                )
            )
            name = _text(
                _value(
                    row,
                    "name",
                    "nome",
                )
            )

            if (
                    legacy_id is None
                    or legacy_source not in valid_sources
                    or len(legacy_key) != 64
                    or not name
            ):
                counters.skipped += 1
                counters.errors.append(
                    "Etapa ignorada sem identidade, origem ou nome válido: "
                    f"{row!r}"
                )
                continue

            identity = (
                legacy_source,
                legacy_id,
            )

            if identity in imported_identities:
                counters.skipped += 1
                counters.errors.append(
                    "Etapa duplicada na resposta do bridge: "
                    f"{identity!r}"
                )
                continue

            imported_identities.add(identity)

            raw_payload = _value(
                row,
                "legacy_payload",
                default={},
            )

            if not isinstance(raw_payload, dict):
                raw_payload = {
                    "value": raw_payload,
                }

            values = {
                "legacy_key": legacy_key,
                "code": _text(
                    _value(
                        row,
                        "code",
                        "codigo",
                    )
                ),
                "name": name,
                "legacy_category": _text(
                    _value(
                        row,
                        "category",
                        "categoria",
                    )
                ),
                "is_active": bool(
                    _value(
                        row,
                        "is_active",
                        default=True,
                    )
                ),
                "legacy_payload": raw_payload,
                "legacy_payload_hash": _hash(row),
            }

            existing = existing_by_identity.get(identity)

            if dry_run:
                if existing is None:
                    counters.created += 1
                elif _has_changes(existing, values):
                    counters.updated += 1
                    imported_pks.add(existing.pk)
                else:
                    counters.unchanged += 1
                    imported_pks.add(existing.pk)

                continue

            lookup = {
                "origin": DataOrigin.LEGACY,
                "legacy_source": legacy_source,
                "legacy_id": legacy_id,
            }

            with transaction.atomic():
                stage, created = BudgetStageCatalog.objects.get_or_create(
                    **lookup,
                    defaults={
                        **values,
                        "imported_at": timezone.now(),
                    },
                )

                if created:
                    counters.created += 1
                    existing_by_identity[identity] = stage
                elif _has_changes(stage, values):
                    _apply_changes(stage, values)
                    counters.updated += 1
                else:
                    counters.unchanged += 1

                imported_pks.add(stage.pk)

        # Uma resposta vazia não desativa o catálogo inteiro.
        if imported_identities:
            missing_queryset = BudgetStageCatalog.objects.filter(
                origin=DataOrigin.LEGACY,
                legacy_source__in=BudgetStageLegacySource.values,
                is_active=True,
            ).exclude(
                pk__in=imported_pks,
            )

            if dry_run:
                counters.deactivated = missing_queryset.count()
            else:
                counters.deactivated = missing_queryset.update(
                    is_active=False,
                )

        return counters

    def import_supplies(self, *, dry_run: bool = False) -> ImportCounters:
        units_by_abbreviation: dict[str, UnitMeasure] = {}
        for unit in UnitMeasure.objects.filter(ativo=True).order_by("legacy_id"):
            # Havendo siglas duplicadas no legado, mantém a unidade canônica
            # com o menor legacy_id.
            units_by_abbreviation.setdefault(_key(unit.sigla), unit)

        active_groups = list(MaterialGroup.objects.filter(ativo=True))
        groups_by_name = {
            _reference_name_key(group.nome): group for group in active_groups
        }
        groups_by_legacy_id: dict[int, MaterialGroup] = {}
        ambiguous_group_ids: set[int] = set()
        for group in active_groups:
            if group.legacy_id in groups_by_legacy_id:
                ambiguous_group_ids.add(group.legacy_id)
                groups_by_legacy_id.pop(group.legacy_id, None)
                continue

            if group.legacy_id not in ambiguous_group_ids:
                groups_by_legacy_id[group.legacy_id] = group
        counters = ImportCounters()
        existing_by_legacy_id = {}
        if dry_run:
            existing_by_legacy_id = {
                supply.legacy_id: supply
                for supply in Supply.objects.select_related(
                    "unit_measure",
                    "material_group",
                ).filter(
                    origin=DataOrigin.LEGACY,
                    legacy_table=self.SUPPLY_TABLE,
                    legacy_id__isnull=False,
                )
            }

        for row in self.client.iter_resource("supplies"):
            counters.read += 1
            self._report_progress("supplies", counters)
            legacy_id = _integer(
                _value(
                    row,
                    "insumoCodigo",
                    "insumoId",
                    "insumoID",
                    "codigo",
                    "id",
                )
            )
            description = _text(
                _value(
                    row,
                    "insumoDescricao",
                    "descricao",
                    "ESPECIFICAÇÃO",
                    "item",
                )
            )

            if legacy_id is None or not description:
                counters.skipped += 1
                counters.errors.append(f"Insumo ignorado sem id/descrição: {row!r}")
                continue

            unit_text = _text(
                _value(
                    row,
                    "insumoUnidade",
                    "unidade",
                    "Unid",
                )
            )

            group_legacy_id = _integer(
                _value(
                    row,
                    "grupoDeMaterialID",
                    "grupoDeMaterialId",
                )
            )
            group_name = _canonical_group_name(
                _value(
                    row,
                    "grupoDeMaterialNome",
                    "grupoMaterialNome",
                )
            )

            unit_measure = units_by_abbreviation.get(_key(unit_text))

            material_group_by_id = groups_by_legacy_id.get(group_legacy_id)

            material_group_by_name = None

            if group_name:
                material_group_by_name = groups_by_name.get(
                    _reference_name_key(group_name)
                )

            # O tblInsumos possui IDs históricos associados a nomes
            # diferentes. Quando o nome encontra um grupo canônico,
            # ele é mais confiável do que o ID inconsistente.
            material_group = material_group_by_name or material_group_by_id

            values = {
                "description": description,
                "supply_type": _supply_type(
                    _value(
                        row,
                        "insumoTipo",
                        "tipo",
                    )
                ),
                "unit": unit_text,
                "unit_measure": unit_measure,
                "material_group": material_group,
                "full_description": _text(
                    _value(
                        row,
                        "insumoDescricaoCompleta",
                        "descricaoCompleta",
                    )
                )
                or description,
                "specification": _text(
                    _value(
                        row,
                        "insumoEspecificacaoComplementar",
                        "insumoEspecificacao",
                        "ESPECCOM",
                        "especificacao",
                    )
                ),
                "is_active": True,
                "legacy_payload": row,
                "legacy_payload_hash": _hash(row),
            }

            lookup = {
                "origin": DataOrigin.LEGACY,
                "legacy_table": self.SUPPLY_TABLE,
                "legacy_id": legacy_id,
            }

            existing = (
                existing_by_legacy_id.get(legacy_id)
                if dry_run
                else Supply.objects.select_related(
                    "unit_measure",
                    "material_group",
                )
                .filter(**lookup)
                .first()
            )
            if dry_run:
                if existing is None:
                    counters.created += 1
                elif _has_changes(existing, values):
                    counters.updated += 1
                else:
                    counters.unchanged += 1
                continue

            with transaction.atomic():
                supply, created = Supply.objects.get_or_create(
                    **lookup,
                    defaults={**values, "imported_at": timezone.now()},
                )
                if created:
                    counters.created += 1
                elif _has_changes(supply, values):
                    _apply_changes(supply, values)
                    counters.updated += 1
                else:
                    counters.unchanged += 1

        return counters

    def import_measurement_units(
        self,
        *,
        dry_run: bool = False,
    ) -> ImportCounters:
        counters = ImportCounters()
        imported_ids: set[int] = set()

        existing_by_legacy_id = {
            unit.legacy_id: unit
            for unit in UnitMeasure.objects.filter(
                legacy_id__isnull=False,
            )
        }

        for row in self.client.iter_resource("measurement-units"):
            counters.read += 1
            self._report_progress(
                "measurement-units",
                counters,
            )

            legacy_id = _integer(
                _value(
                    row,
                    "unidadeDeMedidaId",
                    "unidadeDeMedidaID",
                    "id",
                )
            )
            nome = _text(
                _value(
                    row,
                    "unidadeDeMedidaNome",
                    "nome",
                )
            )
            sigla = _text(
                _value(
                    row,
                    "unidadeDeMedidaSigla",
                    "sigla",
                )
            )

            if legacy_id is None or not sigla:
                counters.skipped += 1
                counters.errors.append(f"Unidade ignorada sem ID/sigla: {row!r}")
                continue

            imported_ids.add(legacy_id)

            values = {
                "nome": nome or sigla,
                "sigla": sigla,
                "ativo": True,
            }

            existing = existing_by_legacy_id.get(legacy_id)

            if dry_run:
                if existing is None:
                    counters.created += 1
                elif _has_changes(existing, values):
                    counters.updated += 1
                else:
                    counters.unchanged += 1
                continue

            with transaction.atomic():
                unit, created = UnitMeasure.objects.get_or_create(
                    legacy_id=legacy_id,
                    defaults=values,
                )

                if created:
                    counters.created += 1
                    existing_by_legacy_id[legacy_id] = unit
                elif _has_changes(unit, values):
                    for field_name, value in values.items():
                        setattr(unit, field_name, value)

                    unit.save()
                    counters.updated += 1
                else:
                    counters.unchanged += 1

        if imported_ids:
            missing_queryset = UnitMeasure.objects.filter(ativo=True).exclude(
                legacy_id__in=imported_ids
            )

            if dry_run:
                counters.deactivated = missing_queryset.count()
            else:
                counters.deactivated = missing_queryset.update(ativo=False)

        return counters

    def import_material_groups(
        self,
        *,
        dry_run: bool = False,
    ) -> ImportCounters:
        counters = ImportCounters()
        groups_by_name: dict[str, dict[str, Any]] = {}

        # A tabela possui poucos registros. Carregamos todos
        # para eliminar nomes duplicados antes do upsert.
        for row in self.client.iter_resource("supply-groups"):
            counters.read += 1
            self._report_progress(
                "supply-groups",
                counters,
            )

            legacy_id = _integer(
                _value(
                    row,
                    "grupoDeMaterialID",
                    "grupoDeMaterialId",
                    "legacy_id",
                    "id",
                )
            )
            name = _canonical_group_name(
                _value(
                    row,
                    "grupoDeMaterialNome",
                    "name",
                    "nome",
                )
            )

            if legacy_id is None or not name:
                counters.skipped += 1
                counters.errors.append(f"Grupo ignorado sem ID/nome: {row!r}")
                continue

            normalized_name = _reference_name_key(name)
            existing = groups_by_name.get(normalized_name)

            if existing is None or legacy_id < existing["legacy_id"]:
                groups_by_name[normalized_name] = {
                    "legacy_id": legacy_id,
                    "nome": name,
                }

        existing_by_name: dict[str, MaterialGroup] = {}
        for group in MaterialGroup.objects.all().order_by("pk"):
            existing_by_name.setdefault(
                _reference_name_key(group.nome),
                group,
            )

        imported_pks: set[int] = set()

        for group_data in sorted(
            groups_by_name.values(),
            key=lambda item: item["legacy_id"],
        ):
            legacy_id = group_data["legacy_id"]
            values = {
                "legacy_id": legacy_id,
                "nome": group_data["nome"],
                "ativo": True,
            }
            normalized_name = _reference_name_key(group_data["nome"])
            existing = existing_by_name.get(normalized_name)

            if dry_run:
                if existing is None:
                    counters.created += 1
                elif _has_changes(existing, values):
                    counters.updated += 1
                else:
                    counters.unchanged += 1

                if existing is not None:
                    imported_pks.add(existing.pk)
                continue

            with transaction.atomic():
                group = existing
                created = group is None

                if group is None:
                    group = MaterialGroup.objects.create(**values)
                    existing_by_name[normalized_name] = group

                if created:
                    counters.created += 1
                elif _has_changes(group, values):
                    for field_name, value in values.items():
                        setattr(group, field_name, value)

                    group.save()
                    counters.updated += 1
                else:
                    counters.unchanged += 1

                imported_pks.add(group.pk)

        if groups_by_name:
            missing_queryset = MaterialGroup.objects.filter(ativo=True).exclude(
                pk__in=imported_pks
            )

            if dry_run:
                counters.deactivated = missing_queryset.count()
            else:
                counters.deactivated = missing_queryset.update(ativo=False)

        return counters

    def import_compositions(self, *, dry_run: bool = False) -> ImportCounters:
        counters = ImportCounters()
        existing_by_legacy_id = {}
        if dry_run:
            existing_by_legacy_id = {
                composition.legacy_id: composition
                for composition in ServiceComposition.objects.filter(
                    origin=DataOrigin.LEGACY,
                    legacy_table=self.COMPOSITION_TABLE,
                    legacy_id__isnull=False,
                ).prefetch_related("versions")
            }

        for row in self.client.iter_resource("service-compositions"):
            counters.read += 1
            self._report_progress("compositions", counters)
            legacy_id = _integer(
                _value(
                    row,
                    "composicaoDeServicoId",
                    "composicaoServicoId",
                    "id",
                )
            )
            name = _text(_value(row, "composicaoDeServicoNome", "nome", "descricao"))

            if legacy_id is None or not name:
                counters.skipped += 1
                counters.errors.append(f"Composição ignorada sem id/nome: {row!r}")
                continue

            composition_values = {
                "code": _text(
                    _value(
                        row,
                        "codigoParaVincular",
                        "composicaoDeServicoCodigo",
                        "codigo",
                        "TCPO",
                    )
                ),
                "name": name,
                "is_active": True,
            }
            version_values = {
                "status": CompositionStatus.HISTORICAL,
                "origin": DataOrigin.LEGACY,
                "unit": _text(
                    _value(
                        row,
                        "composicaoDeServicoUnidadeDeMedida",
                        "composicaoDeServicoUnidade",
                        "unidade",
                        "Unid",
                    )
                ),
                # A tabela atual fornece apenas o valor consolidado.
                "material_total": _decimal(_value(row, "valorMAT", "valorMaterial")),
                "labor_total": _decimal(_value(row, "valorMDO", "valorMaoDeObra")),
                "equipment_total": _decimal(
                    _value(row, "valorEquipamento", "valorEquip")
                ),
                "total": _decimal(
                    _value(row, "composicaoDeServicoValor", "valorTotal", "valor")
                ),
                "legacy_payload": row,
                "legacy_payload_hash": _hash(row),
            }
            lookup = {
                "origin": DataOrigin.LEGACY,
                "legacy_table": self.COMPOSITION_TABLE,
                "legacy_id": legacy_id,
            }

            existing = (
                existing_by_legacy_id.get(legacy_id)
                if dry_run
                else ServiceComposition.objects.filter(**lookup).first()
            )
            existing_version = (
                existing.versions.filter(number=1).first() if existing else None
            )
            has_changes = existing is not None and (
                _has_changes(existing, composition_values)
                or existing_version is None
                or _has_changes(existing_version, version_values)
            )

            if dry_run:
                if existing is None:
                    counters.created += 1
                elif has_changes:
                    counters.updated += 1
                else:
                    counters.unchanged += 1
                continue

            with transaction.atomic():
                composition, created = ServiceComposition.objects.get_or_create(
                    **lookup,
                    defaults=composition_values,
                )
                composition_changed = False
                if not created and _has_changes(composition, composition_values):
                    for field_name, value in composition_values.items():
                        setattr(composition, field_name, value)
                    composition.save(
                        update_fields=(*composition_values.keys(), "updated_at")
                    )
                    composition_changed = True

                version, version_created = (
                    ServiceCompositionVersion.objects.get_or_create(
                        composition=composition,
                        number=1,
                        defaults={
                            **version_values,
                            "imported_at": timezone.now(),
                        },
                    )
                )
                version_changed = False
                if not version_created and _has_changes(version, version_values):
                    _apply_changes(version, version_values)
                    version_changed = True

                if created:
                    counters.created += 1
                elif composition_changed or version_created or version_changed:
                    counters.updated += 1
                else:
                    counters.unchanged += 1

        return counters

    def import_composition_items(self, *, dry_run: bool = False) -> ImportCounters:
        """Importa os componentes das versões históricas do Access.

        A tabela legada não possui o ID do insumo. A associação é feita por
        descrição normalizada + unidade. Quando não há correspondência segura,
        o registro é preservado como item livre em vez de ser descartado.
        """
        counters = ImportCounters()

        versions_by_composition_legacy_id = {
            version.composition.legacy_id: version
            for version in ServiceCompositionVersion.objects.select_related(
                "composition"
            ).filter(
                composition__origin=DataOrigin.LEGACY,
                composition__legacy_table=self.COMPOSITION_TABLE,
                composition__legacy_id__isnull=False,
                number=1,
            )
        }

        legacy_supplies = list(
            Supply.objects.filter(origin=DataOrigin.LEGACY).order_by("pk")
        )
        supplies_by_name_and_unit: dict[tuple[str, str], Supply] = {}
        supplies_by_name: dict[str, Supply] = {}
        ambiguous_supply_names: set[str] = set()

        for supply in legacy_supplies:
            name_key = _reference_name_key(supply.description)
            supplies_by_name_and_unit.setdefault(
                (name_key, _key(supply.unit)),
                supply,
            )
            if name_key in supplies_by_name:
                ambiguous_supply_names.add(name_key)
                supplies_by_name.pop(name_key, None)
            elif name_key not in ambiguous_supply_names:
                supplies_by_name[name_key] = supply

        subcompositions_by_name: dict[str, ServiceComposition] = {}
        ambiguous_composition_names: set[str] = set()
        for composition in ServiceComposition.objects.filter(
            origin=DataOrigin.LEGACY
        ).order_by("pk"):
            name_key = _reference_name_key(composition.name)
            if name_key in subcompositions_by_name:
                ambiguous_composition_names.add(name_key)
                subcompositions_by_name.pop(name_key, None)
            elif name_key not in ambiguous_composition_names:
                subcompositions_by_name[name_key] = composition

        existing_by_legacy_id = {
            item.legacy_id: item
            for item in ServiceCompositionItem.objects.filter(
                legacy_table=self.COMPOSITION_ITEM_TABLE,
                legacy_id__isnull=False,
            )
        }

        for row in self.client.iter_resource("service-composition-items"):
            counters.read += 1
            self._report_progress("composition-items", counters)

            legacy_id = _integer(_value(row, "itemComposicaoDeServicoId", "id"))
            composition_legacy_id = _integer(
                _value(row, "composicaoDeServicoId", "composicaoServicoId")
            )
            description = _text(
                _value(row, "itemComposicaoDeServicoInsumo", "descricao")
            )
            complement = _text(
                _value(row, "itemComposicaoDeServicoComplemento", "complemento")
            )
            unit = _text(
                _value(row, "itemComposicaoDeServicoUnidade", "unidade", "Unid")
            )

            version = versions_by_composition_legacy_id.get(composition_legacy_id)
            if legacy_id is None or version is None or not description:
                counters.skipped += 1
                counters.errors.append(
                    "Item de composição ignorado sem ID, descrição ou versão pai: "
                    f"{row!r}"
                )
                continue

            description_key = _reference_name_key(description)
            is_composed = bool(
                _integer(_value(row, "itemComposicaoDeServicoComposto", default=0))
            )

            supply = None
            subcomposition = None
            item_type = CompositionItemType.FREE_TEXT

            if is_composed:
                subcomposition = subcompositions_by_name.get(description_key)
                if (
                    subcomposition is not None
                    and subcomposition.pk != version.composition_id
                ):
                    item_type = CompositionItemType.SUBCOMPOSITION
                else:
                    subcomposition = None
            else:
                supply = supplies_by_name_and_unit.get(
                    (description_key, _key(unit))
                ) or supplies_by_name.get(description_key)
                if supply is not None:
                    item_type = CompositionItemType.SUPPLY

            unit_price = _decimal(
                _value(row, "itemComposicaoDeServicoValor", "valor")
            )
            material_price = _decimal(
                _value(row, "itemComposicaoDeServicoValorMAT", "valorMAT")
            )
            labor_price = Decimal("0")
            equipment_price = Decimal("0")

            if item_type == CompositionItemType.SUPPLY and supply is not None:
                if supply.supply_type == SupplyType.MATERIAL:
                    material_price = material_price or unit_price
                elif supply.supply_type == SupplyType.EQUIPMENT:
                    equipment_price = unit_price
                else:
                    labor_price = unit_price
            elif material_price < unit_price:
                # O legado separa apenas a parcela material. A parcela restante
                # é mantida em mão de obra quando não existe classificação segura.
                labor_price = unit_price - material_price

            snapshot = description
            if complement:
                snapshot = f"{description} - {complement}"

            values = {
                "version": version,
                "item_type": item_type,
                "supply": supply,
                "subcomposition": subcomposition,
                "description_snapshot": snapshot[:500],
                "unit_snapshot": unit[:30],
                "coefficient": _decimal(
                    _value(row, "itemComposicaoDeServicoQtde", "Qtde", default=0)
                ),
                "material_unit_price": material_price,
                "labor_unit_price": labor_price,
                "equipment_unit_price": equipment_price,
                "position": legacy_id,
            }
            existing = existing_by_legacy_id.get(legacy_id)

            if dry_run:
                if existing is None:
                    counters.created += 1
                elif _has_changes(existing, values):
                    counters.updated += 1
                else:
                    counters.unchanged += 1
                continue

            with transaction.atomic():
                item, created = ServiceCompositionItem.objects.get_or_create(
                    legacy_table=self.COMPOSITION_ITEM_TABLE,
                    legacy_id=legacy_id,
                    defaults=values,
                )
                if created:
                    counters.created += 1
                    existing_by_legacy_id[legacy_id] = item
                elif _has_changes(item, values):
                    for field_name, value in values.items():
                        setattr(item, field_name, value)
                    item.save(update_fields=tuple(values.keys()))
                    counters.updated += 1
                else:
                    counters.unchanged += 1

        return counters
