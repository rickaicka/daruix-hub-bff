import re
import unicodedata

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from commercial.models import (
    BusinessSegment,
    CatalogOrigin,
    CompanyType,
    Party,
    PartyType,
    PersonType,
)
from integrations.legacy_bridge import LegacyBridgeClient, LegacyBridgeHttpError


def normalize_catalog_name(value: object) -> str:
    normalized = str(value or "").strip().upper()

    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = "".join(
        char
        for char in normalized
        if not unicodedata.combining(char)
    )

    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)

    return normalized.strip()


# Somente aliases semanticamente seguros para destinos que existem
# no catálogo local de BusinessSegment.
BUSINESS_SEGMENT_ALIASES: dict[str, str] = {
    "ARQUITETURA DESIGNER": "ARQUITETURA",

    "ENGENHEIRO": "ENGENHARIA",

    "GERENCIAMENTO E FISCALIZACAO": "GERENCIAMENTO",
    "GERENCIADORA": "GERENCIAMENTO",

    "PROJETOS INSTALACOES": "PROJETO INSTALACOES HIDRAULICAS",
    "PROJETISTA INSTALACOES HIDRAULICAS":
        "PROJETO INSTALACOES HIDRAULICAS",

    "INSTALACAO ELETRICA":
        "INSTALACOES ELETRICAS MAO DE OBRA",
}


def optional_text(
    value: object,
    *,
    max_length: int | None = None,
) -> str:
    result = str(value or "").strip()
    return result[:max_length] if max_length else result


class Command(BaseCommand):
    help = (
        "Sincroniza ramos empresariais, tipos de empresa e clientes "
        "do Access via Legacy Bridge."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        try:
            client = LegacyBridgeClient()

            business_segments = client.list_business_segments()
            company_types = client.list_company_types()
            clients = client.list_clients_catalog()

        except LegacyBridgeHttpError as error:
            raise CommandError(str(error)) from error

        with transaction.atomic():
            segment_stats = self._sync_catalog(
                BusinessSegment,
                business_segments,
            )
            self._write_stats(
                "ramos empresariais",
                segment_stats,
            )

            type_stats = self._sync_catalog(
                CompanyType,
                company_types,
            )
            self._write_stats(
                "tipos de empresa",
                type_stats,
            )

            client_stats = self._sync_clients(
                clients
            )
            self._write_stats(
                "clientes",
                client_stats,
            )

            self.stdout.write(
                "clientes: tipo não resolvido="
                f"{client_stats['unresolved_company_type']}, "
                "ramo não resolvido="
                f"{client_stats['unresolved_business_segment']}, "
                "sem ramo="
                f"{client_stats['without_business_segment']}, "
                "sem documento="
                f"{client_stats['without_document']}"
            )

            if dry_run:
                transaction.set_rollback(True)

                self.stdout.write(
                    self.style.WARNING(
                        "Dry-run: nenhuma alteração persistida."
                    )
                )

    def _write_stats(
        self,
        label: str,
        stats: dict[str, int],
    ) -> None:
        self.stdout.write(
            f"{label}: "
            f"criados={stats['created']}, "
            f"atualizados={stats['updated']}, "
            f"inalterados={stats['unchanged']}, "
            f"desativados={stats['deactivated']}"
        )

    @staticmethod
    def _sync_catalog(model, items):
        stats = {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "deactivated": 0,
        }

        received_keys: set[str] = set()

        for item in items:
            legacy_key = str(
                item.get("legacy_key") or ""
            ).strip()

            if len(legacy_key) != 64:
                raise CommandError(
                    f"Item legado inválido: {item!r}"
                )

            raw_legacy_id = item.get("legacy_id")

            try:
                legacy_id = (
                    int(raw_legacy_id)
                    if raw_legacy_id is not None
                    else None
                )

            except (TypeError, ValueError) as error:
                raise CommandError(
                    f"legacy_id inválido: {item!r}"
                ) from error

            name = optional_text(
                item.get("name"),
                max_length=150,
            )

            if not name:
                raise CommandError(
                    f"Item legado sem nome: {item!r}"
                )

            received_keys.add(
                legacy_key
            )

            instance = model.objects.filter(
                legacy_key=legacy_key
            ).first()

            if instance is None:
                model.objects.create(
                    legacy_id=legacy_id,
                    legacy_key=legacy_key,
                    name=name,
                    origin=CatalogOrigin.LEGACY,
                    is_active=True,
                    legacy_payload=item,
                )

                stats["created"] += 1
                continue

            changed = (
                instance.name != name
                or instance.legacy_id != legacy_id
                or not instance.is_active
                or instance.legacy_payload != item
                or instance.origin != CatalogOrigin.LEGACY
            )

            if changed:
                instance.name = name
                instance.legacy_id = legacy_id
                instance.origin = CatalogOrigin.LEGACY
                instance.is_active = True
                instance.legacy_payload = item

                instance.save(
                    update_fields=(
                        "legacy_id",
                        "name",
                        "origin",
                        "is_active",
                        "legacy_payload",
                        "updated_at",
                    )
                )

                stats["updated"] += 1

            else:
                stats["unchanged"] += 1

        stale = model.objects.filter(
            origin=CatalogOrigin.LEGACY,
            is_active=True,
        ).exclude(
            legacy_key__in=received_keys
        )

        stats["deactivated"] = stale.update(
            is_active=False
        )

        return stats

    @staticmethod
    def _catalog_by_name(model) -> dict[str, object]:
        result: dict[str, object] = {}

        for item in model.objects.filter(
            is_active=True
        ):
            key = normalize_catalog_name(
                item.name
            )

            if key:
                result[key] = item

        return result

    @staticmethod
    def _resolve_business_segment(
        raw_name: str,
        business_segments: dict[str, object],
    ):
        if not raw_name:
            return None

        segment_key = normalize_catalog_name(
            raw_name
        )

        target_key = BUSINESS_SEGMENT_ALIASES.get(
            segment_key,
            segment_key,
        )

        return business_segments.get(
            target_key
        )

    def _sync_clients(self, items):
        stats = {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "deactivated": 0,
            "unresolved_company_type": 0,
            "unresolved_business_segment": 0,
            "without_business_segment": 0,
            "without_document": 0,
        }

        received_keys: set[str] = set()

        company_types = self._catalog_by_name(
            CompanyType
        )

        business_segments = self._catalog_by_name(
            BusinessSegment
        )

        for item in items:
            legacy_key = str(
                item.get("legacy_key") or ""
            ).strip()

            if len(legacy_key) != 64:
                raise CommandError(
                    f"Cliente legado inválido: {item!r}"
                )

            raw_legacy_id = item.get("legacy_id")

            try:
                legacy_id = (
                    int(raw_legacy_id)
                    if raw_legacy_id is not None
                    else None
                )

            except (TypeError, ValueError) as error:
                raise CommandError(
                    f"legacy_id inválido: {item!r}"
                ) from error

            legal_name = optional_text(
                item.get("name"),
                max_length=180,
            )

            if not legal_name:
                raise CommandError(
                    f"Cliente legado sem nome: {item!r}"
                )

            company_type_name = optional_text(
                item.get("company_type_name")
            )

            segment_name = optional_text(
                item.get(
                    "business_segment_name"
                )
            )

            company_type_key = normalize_catalog_name(
                company_type_name
            )

            company_type = company_types.get(
                company_type_key
            )

            business_segment = (
                self._resolve_business_segment(
                    segment_name,
                    business_segments,
                )
            )

            if (
                company_type_name
                and company_type is None
            ):
                stats[
                    "unresolved_company_type"
                ] += 1

            if not segment_name:
                stats[
                    "without_business_segment"
                ] += 1

            elif business_segment is None:
                stats[
                    "unresolved_business_segment"
                ] += 1

            person_type = (
                PersonType.INDIVIDUAL
                if (
                    "FISICA" in company_type_key
                    or "PESSOA FISICA"
                    in company_type_key
                )
                else PersonType.COMPANY
            )

            document = (
                optional_text(
                    item.get("document"),
                    max_length=20,
                )
                or None
            )

            if document is None:
                stats[
                    "without_document"
                ] += 1

            payload = dict(
                item.get("legacy_payload")
                or {}
            )

            payload.update(
                {
                    # Valores originais do legado são preservados
                    # mesmo quando a FK foi resolvida por alias.
                    "company_type_name":
                        company_type_name,
                    "business_segment_name":
                        segment_name,

                    "address": optional_text(
                        item.get("address")
                    ),
                    "district": optional_text(
                        item.get("district")
                    ),
                    "city": optional_text(
                        item.get("city")
                    ),
                    "state": optional_text(
                        item.get("state")
                    ),
                    "postal_code": optional_text(
                        item.get("postal_code")
                    ),
                    "phone": optional_text(
                        item.get("phone")
                    ),
                    "email": optional_text(
                        item.get("email")
                    ),
                }
            )

            defaults = {
                "origin": CatalogOrigin.LEGACY,
                "legacy_id": legacy_id,
                "legacy_payload": payload,
                "party_type": PartyType.CLIENT,
                "person_type": person_type,
                "legal_name": legal_name,

                "trade_name": optional_text(
                    item.get("trade_name"),
                    max_length=150,
                ),

                "document": document,

                "state_registration":
                    optional_text(
                        payload.get("ie_rg"),
                        max_length=30,
                    ),

                "business_segment":
                    business_segment,

                "company_type":
                    company_type,

                "last_service": optional_text(
                    item.get("last_service")
                    or payload.get("last_service")
                    or payload.get("ultimo_servico")
                    or payload.get("ultimo_servico_solicitado"),
                    max_length=180,
                ),

                "referred_by": optional_text(
                    item.get("referred_by")
                    or payload.get("indicado_por"),
                    max_length=180,
                ),

                "website": optional_text(
                    item.get("website"),
                    max_length=200,
                ),

                "is_active": True,
            }

            received_keys.add(
                legacy_key
            )

            instance = Party.objects.filter(
                legacy_key=legacy_key
            ).first()

            if (
                    instance is None
                    and legacy_id is not None
            ):
                instance = Party.objects.filter(
                    origin=CatalogOrigin.LEGACY,
                    legacy_id=legacy_id,
                ).first()

            if instance is None:
                Party.objects.create(
                    legacy_key=legacy_key,
                    **defaults,
                )

                stats["created"] += 1
                continue

            changed_fields: list[str] = []

            if instance.legacy_key != legacy_key:
                instance.legacy_key = legacy_key
                changed_fields.append(
                    "legacy_key"
                )

            for field, value in defaults.items():
                current = getattr(
                    instance,
                    field,
                )

                current_value = (
                    current.pk
                    if hasattr(current, "pk")
                    else current
                )

                new_value = (
                    value.pk
                    if hasattr(value, "pk")
                    else value
                )

                if current_value != new_value:
                    setattr(
                        instance,
                        field,
                        value,
                    )

                    changed_fields.append(
                        field
                    )

            if changed_fields:
                instance.save(
                    update_fields=(
                        *changed_fields,
                        "updated_at",
                    )
                )

                stats["updated"] += 1

            else:
                stats["unchanged"] += 1

        stale = Party.objects.filter(
            origin=CatalogOrigin.LEGACY,
            party_type=PartyType.CLIENT,
            is_active=True,
        ).exclude(
            legacy_key__in=received_keys
        )

        stats["deactivated"] = stale.update(
            is_active=False
        )

        return stats
