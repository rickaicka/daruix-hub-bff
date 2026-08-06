from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone

from budgeting.choices import CompositionStatus, DataOrigin, SupplyType
from budgeting.models import ServiceComposition, ServiceCompositionVersion, Supply

from .legacy_bridge import LegacyBudgetingClient


def _key(value: Any) -> str:
    """Normaliza nomes de colunas sem alterar os valores vindos do legado."""
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
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
        str(value)
        .strip()
        .replace("R$", "")
        .replace("\u00a0", "")
        .replace(" ", "")
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
    """
    Classifica somente valores textuais conhecidos.

    No Access atual, ``insumoTipo`` é numérico e seu domínio ainda não foi
    confirmado. Esses valores permanecem como OTHER e continuam disponíveis
    integralmente em ``legacy_payload``.
    """
    normalized = _key(value)
    if "material" in normalized:
        return SupplyType.MATERIAL
    if "mao" in normalized or "mdo" in normalized:
        return SupplyType.LABOR
    if "equip" in normalized:
        return SupplyType.EQUIPMENT
    return SupplyType.OTHER


def _has_changes(instance: Any, values: dict[str, Any]) -> bool:
    return any(getattr(instance, field_name) != value for field_name, value in values.items())


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
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "read": self.read,
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "skipped": self.skipped,
            "errors": len(self.errors),
        }


class LegacyCatalogImporter:
    SUPPLY_TABLE = "tblInsumos"
    COMPOSITION_TABLE = "tblComposicaoDeServico"

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

    def import_supplies(self, *, dry_run: bool = False) -> ImportCounters:
        counters = ImportCounters()
        existing_by_legacy_id = {}
        if dry_run:
            existing_by_legacy_id = {
                supply.legacy_id: supply
                for supply in Supply.objects.filter(
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
                counters.errors.append(
                    f"Insumo ignorado sem id/descrição: {row!r}"
                )
                continue

            values = {
                "code": _text(
                    _value(row, "insumoCodigo", "TCPO", "codigoExterno")
                ),
                "description": description,
                "supply_type": _supply_type(_value(row, "insumoTipo", "tipo")),
                "unit": _text(_value(row, "insumoUnidade", "unidade", "Unid")),
                "specification": _text(
                    _value(
                        row,
                        "insumoEspecificacaoComplementar",
                        "insumoEspecificacao",
                        "ESPECCOM",
                        "especificacao",
                    )
                ),
                # O significado de insumoFiltro ainda não foi confirmado.
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
                else Supply.objects.filter(**lookup).first()
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
            name = _text(
                _value(row, "composicaoDeServicoNome", "nome", "descricao")
            )

            if legacy_id is None or not name:
                counters.skipped += 1
                counters.errors.append(
                    f"Composição ignorada sem id/nome: {row!r}"
                )
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
                "material_total": _decimal(
                    _value(row, "valorMAT", "valorMaterial")
                ),
                "labor_total": _decimal(
                    _value(row, "valorMDO", "valorMaoDeObra")
                ),
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
            has_changes = (
                existing is not None
                and (
                    _has_changes(existing, composition_values)
                    or existing_version is None
                    or _has_changes(existing_version, version_values)
                )
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
