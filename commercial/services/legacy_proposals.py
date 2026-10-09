from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Callable, Iterable

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from commercial.models import (
    CatalogOrigin,
    Contact,
    Department,
    Division,
    InstallmentSource,
    InstallmentStatus,
    Party,
    PartyType,
    PersonType,
    Project,
    Proposal,
    ProposalContact,
    ProposalContactContext,
    ProposalInstallment,
    ProposalRequestedService,
    ProposalStatus,
    ProposalType,
)


MOJIBAKE_MARKERS = ("Ã", "Â", "â", "�")
LEGACY_TEXT_REPLACEMENTS = {
    "ÃÃ": "ÇÃ",
    "Ãnica": "Única",
    "ÃNICA": "ÚNICA",
    "ANÃLISE": "ANÁLISE",
    "AnÃ¡lise": "Análise",
    "Ãrea": "Área",
    "ÃREA": "ÁREA",
    "METÃLICA": "METÁLICA",
    "TÃCNICA": "TÉCNICA",
    "TÃ©cnica": "Técnica",
    "RESIDÃNCIA": "RESIDÊNCIA",
    "ELÃTRICAS": "ELÉTRICAS",
    "HIDRÃULICAS": "HIDRÁULICAS",
    "MAUÃ": "MAUÁ",
}


def repair_legacy_text(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    for _ in range(2):
        try:
            candidate = text.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break

        current_markers = sum(text.count(marker) for marker in MOJIBAKE_MARKERS)
        candidate_markers = sum(candidate.count(marker) for marker in MOJIBAKE_MARKERS)
        if candidate_markers >= current_markers:
            break
        text = candidate

    for broken, repaired in LEGACY_TEXT_REPLACEMENTS.items():
        text = text.replace(broken, repaired)

    return text.strip()


def normalize_legacy_text(value: object) -> str:
    text = repair_legacy_text(value).upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return " ".join(text.split())


def legacy_value(row: dict[str, Any], *names: str) -> Any:
    normalized = {
        normalize_legacy_text(key): value
        for key, value in row.items()
    }
    for name in names:
        key = normalize_legacy_text(name)
        if key in normalized:
            return normalized[key]
    return None


def legacy_key(resource: str, identity: object) -> str:
    return hashlib.sha256(
        f"{resource}|{identity}".encode("utf-8")
    ).hexdigest()


def optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def optional_decimal(
    value: object,
    default: Decimal | None = None,
    *,
    decimal_places: int = 2,
) -> Decimal | None:
    quantizer = Decimal(1).scaleb(-decimal_places)
    if value in (None, ""):
        return (
            default.quantize(quantizer, rounding=ROUND_HALF_UP)
            if default is not None
            else None
        )
    try:
        parsed = Decimal(
            str(value)
            .replace("R$", "")
            .replace(" ", "")
            .replace(",", ".")
        )
        return parsed.quantize(quantizer, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return (
            default.quantize(quantizer, rounding=ROUND_HALF_UP)
            if default is not None
            else None
        )


def optional_date(value: object) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def optional_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    if timezone.is_naive(parsed):
        return timezone.make_aware(
            parsed,
            timezone.get_current_timezone(),
        )
    return parsed


def proposal_status(value: object) -> str:
    normalized = normalize_legacy_text(value)
    if normalized in {"APROVADO", "APROVADA", "ACEITO", "ACEITA"}:
        return ProposalStatus.ACCEPTED
    if normalized in {"RECUSADO", "RECUSADA", "REPROVADO", "REPROVADA", "PERDIDA"}:
        return ProposalStatus.REJECTED
    if normalized in {"CANCELADO", "CANCELADA"}:
        return ProposalStatus.CANCELLED
    if normalized in {"ENVIADO", "ENVIADA", "ENTREGUE"}:
        return ProposalStatus.SENT
    if normalized in {"EM ABERTO", "EM ELABORACAO", "ORCAMENTO"}:
        return ProposalStatus.BUDGETING
    return ProposalStatus.REQUESTED


def installment_status(value: object) -> str:
    normalized = normalize_legacy_text(value)
    if normalized in {"QUITADO", "QUITADA", "PAGO", "PAGA"}:
        return InstallmentStatus.PAID
    if normalized in {"EM ABERTO", "ABERTO", "ABERTA"}:
        return InstallmentStatus.OPEN
    if normalized in {"CANCELADO", "CANCELADA"}:
        return InstallmentStatus.CANCELLED
    return InstallmentStatus.UNKNOWN


def _row_identity(row: dict[str, Any], id_names: tuple[str, ...], fallback: str) -> str:
    raw_id = legacy_value(row, *id_names)
    return f"id:{raw_id}" if raw_id not in (None, "") else fallback


class LegacyProposalImporter:
    def __init__(
        self,
        *,
        progress_callback: Callable[[int, int], None] | None = None,
        progress_every: int = 250,
    ) -> None:
        self.stats = defaultdict(int)
        self.progress_callback = progress_callback
        self.progress_every = max(progress_every, 1)
        self._divisions: dict[str, Division] = {}
        self._departments: dict[str, Department] = {}
        self._projects_by_id: dict[int, Project] = {}
        self._projects_by_name: dict[str, Project] = {}
        self._proposal_types: dict[str, ProposalType] = {}
        self._users: dict[str, Any] = {}

        parties = list(Party.objects.all())
        self._parties_by_legacy_id = {
            item.legacy_id: item
            for item in parties
            if item.legacy_id is not None
        }
        self._parties_by_name: dict[str, Party] = {}
        for item in parties:
            for name in (item.legal_name, item.trade_name):
                normalized = normalize_legacy_text(name)
                if normalized and normalized not in self._parties_by_name:
                    self._parties_by_name[normalized] = item

        proposals = list(Proposal.objects.all())
        self._proposals_by_legacy_key = {
            item.legacy_key: item
            for item in proposals
            if item.legacy_key
        }
        self._proposals_by_legacy_id = {
            item.legacy_id: item
            for item in proposals
            if item.legacy_id is not None
        }
        self._proposals_by_code = {
            normalize_legacy_text(item.code): item
            for item in proposals
            if item.code
        }

        self._service_proposal_ids = set(
            ProposalRequestedService.objects.filter(
                origin=CatalogOrigin.LEGACY
            ).values_list("proposal_id", flat=True)
        )
        self._contact_proposal_ids = set(
            ProposalContact.objects.filter(
                origin=CatalogOrigin.LEGACY
            ).values_list("proposal_id", flat=True)
        )
        self._installment_proposal_ids = set(
            ProposalInstallment.objects.exclude(
                source=InstallmentSource.HUB
            ).values_list("proposal_id", flat=True)
        )

    @transaction.atomic
    def import_all(
        self,
        *,
        proposal_types: Iterable[dict[str, Any]],
        departments: Iterable[dict[str, Any]],
        projects: Iterable[dict[str, Any]],
        proposals: Iterable[dict[str, Any]],
        requested_services: Iterable[dict[str, Any]],
        proposal_contacts: Iterable[dict[str, Any]],
        payment_installments: Iterable[dict[str, Any]],
        payment_plans: Iterable[dict[str, Any]],
    ) -> dict[str, int]:
        proposal_rows = list(proposals)
        service_rows = list(requested_services)
        contact_rows = list(proposal_contacts)
        installment_rows = list(payment_installments)
        payment_plan_rows = list(payment_plans)

        self._sync_departments(departments)
        self._sync_projects(projects)
        self._sync_proposal_types(proposal_types)

        services_by_proposal_id, services_by_pc = self._group_services(service_rows)
        contacts_by_pc = self._group_by_pc(contact_rows, "contatoPC")
        installments_by_pc = self._group_by_pc(installment_rows, "pppPC")
        payment_plans_by_pc = self._group_by_pc(payment_plan_rows, "PC")

        total_proposals = len(proposal_rows)
        for processed, row in enumerate(proposal_rows, start=1):
            proposal = self._sync_proposal(row)
            if proposal is None:
                self._notify_progress(processed, total_proposals)
                continue

            legacy_id = optional_int(legacy_value(row, "propostaID"))
            pc = repair_legacy_text(legacy_value(row, "PC"))

            related_services = services_by_proposal_id.get(legacy_id, [])
            if not related_services:
                related_services = services_by_pc.get(normalize_legacy_text(pc), [])

            self._sync_services(proposal, related_services)
            self._sync_contacts(proposal, row, contacts_by_pc.get(normalize_legacy_text(pc), []))

            preferred_installments = installments_by_pc.get(normalize_legacy_text(pc), [])
            if preferred_installments:
                self._sync_installments(
                    proposal,
                    preferred_installments,
                    source=InstallmentSource.LEGACY_INSTALLMENTS,
                )
            else:
                self._sync_installments(
                    proposal,
                    payment_plans_by_pc.get(normalize_legacy_text(pc), []),
                    source=InstallmentSource.LEGACY_PAYMENT_PLAN,
                )

            self._notify_progress(processed, total_proposals)

        return dict(self.stats)

    def _notify_progress(self, processed: int, total: int) -> None:
        if not self.progress_callback:
            return
        if processed == total or processed % self.progress_every == 0:
            self.progress_callback(processed, total)

    def _sync_departments(self, rows: Iterable[dict[str, Any]]) -> None:
        for row in rows:
            division_code = repair_legacy_text(legacy_value(row, "divisao"))
            division = self._resolve_division(division_code, payload=row)

            name = repair_legacy_text(legacy_value(row, "Departamento"))
            if not name:
                continue

            legacy_id = optional_int(legacy_value(row, "departamentoID"))
            key = legacy_key(
                "departments",
                f"id:{legacy_id}" if legacy_id is not None else normalize_legacy_text(name),
            )
            department = Department.objects.filter(legacy_key=key).first()
            if department is None and legacy_id is not None:
                department = Department.objects.filter(legacy_id=legacy_id).first()
            if department is None:
                department = Department.objects.filter(name__iexact=name).first()

            values = {
                "name": name[:150],
                "division": division,
                "abbreviation": repair_legacy_text(
                    legacy_value(row, "departamentoSigla")
                )[:20],
                "origin": CatalogOrigin.LEGACY,
                "legacy_id": legacy_id,
                "legacy_key": key,
                "legacy_payload": row,
                "is_active": True,
            }
            if department is None:
                department = Department.objects.create(**values)
                self.stats["departments_created"] += 1
            else:
                for field, value in values.items():
                    setattr(department, field, value)
                department.save()
                self.stats["departments_updated"] += 1

            self._departments[normalize_legacy_text(name)] = department

    def _resolve_division(
        self,
        code: object,
        *,
        payload: dict[str, Any] | None = None,
    ) -> Division | None:
        clean_code = repair_legacy_text(code).upper()[:20]
        if not clean_code:
            return None
        normalized = normalize_legacy_text(clean_code)
        if normalized in self._divisions:
            return self._divisions[normalized]

        division = Division.objects.filter(code__iexact=clean_code).first()
        key = legacy_key("divisions", normalized)
        values = {
            "name": clean_code,
            "code": clean_code,
            "origin": CatalogOrigin.LEGACY,
            "legacy_key": key,
            "legacy_payload": payload or {},
            "is_active": True,
        }
        if division is None:
            division = Division.objects.create(**values)
            self.stats["divisions_created"] += 1
        else:
            for field, value in values.items():
                setattr(division, field, value)
            division.save()
            self.stats["divisions_updated"] += 1

        self._divisions[normalized] = division
        return division

    def _sync_projects(self, rows: Iterable[dict[str, Any]]) -> None:
        if not self._departments:
            self._departments = {
                normalize_legacy_text(item.name): item
                for item in Department.objects.filter(is_active=True)
            }

        for row in rows:
            name = repair_legacy_text(legacy_value(row, "Projeto"))
            if not name:
                continue
            legacy_id = optional_int(legacy_value(row, "projetoID"))
            department_name = repair_legacy_text(legacy_value(row, "Departamento"))
            department = self._departments.get(normalize_legacy_text(department_name))
            key = legacy_key(
                "projects",
                f"id:{legacy_id}" if legacy_id is not None else normalize_legacy_text(name),
            )
            project = Project.objects.filter(legacy_key=key).first()
            if project is None and legacy_id is not None:
                project = Project.objects.filter(legacy_id=legacy_id).first()
            if project is None:
                project = Project.objects.filter(name__iexact=name).first()

            values = {
                "name": name[:150],
                "department": department,
                "origin": CatalogOrigin.LEGACY,
                "legacy_id": legacy_id,
                "legacy_key": key,
                "legacy_payload": row,
                "is_active": True,
            }
            if project is None:
                project = Project.objects.create(**values)
                self.stats["projects_created"] += 1
            else:
                for field, value in values.items():
                    setattr(project, field, value)
                project.save()
                self.stats["projects_updated"] += 1

            if legacy_id is not None:
                self._projects_by_id[legacy_id] = project
            self._projects_by_name[normalize_legacy_text(name)] = project

    def _sync_proposal_types(self, rows: Iterable[dict[str, Any]]) -> None:
        for row in rows:
            name = repair_legacy_text(legacy_value(row, "tipoDePropostaNome"))
            if not name:
                continue
            legacy_id = optional_int(legacy_value(row, "tipoPropostaID"))
            proposal_type = self._resolve_proposal_type(name, legacy_id=legacy_id)
            proposal_type.legacy_payload = row
            proposal_type.save(update_fields=("legacy_payload", "updated_at"))

    def _resolve_proposal_type(
        self,
        name: object,
        *,
        legacy_id: int | None = None,
    ) -> ProposalType | None:
        clean_name = repair_legacy_text(name)
        normalized = normalize_legacy_text(clean_name)
        if not normalized:
            return None
        if normalized in self._proposal_types:
            return self._proposal_types[normalized]

        key = legacy_key(
            "proposal-types",
            f"id:{legacy_id}" if legacy_id is not None else normalized,
        )
        proposal_type = ProposalType.objects.filter(legacy_key=key).first()
        if proposal_type is None and legacy_id is not None:
            proposal_type = ProposalType.objects.filter(legacy_id=legacy_id).first()
        if proposal_type is None:
            proposal_type = ProposalType.objects.filter(name__iexact=clean_name).first()

        values = {
            "name": clean_name[:150],
            "origin": CatalogOrigin.LEGACY,
            "legacy_id": legacy_id,
            "legacy_key": key,
            "is_active": True,
        }
        if proposal_type is None:
            proposal_type = ProposalType.objects.create(**values)
            self.stats["proposal_types_created"] += 1
        else:
            for field, value in values.items():
                setattr(proposal_type, field, value)
            proposal_type.save()
            self.stats["proposal_types_updated"] += 1

        self._proposal_types[normalized] = proposal_type
        return proposal_type

    @staticmethod
    def _group_by_pc(
        rows: Iterable[dict[str, Any]],
        column: str,
    ) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            pc = normalize_legacy_text(legacy_value(row, column))
            if pc:
                result[pc].append(row)
        return result

    @staticmethod
    def _group_services(
        rows: Iterable[dict[str, Any]],
    ) -> tuple[
        dict[int | None, list[dict[str, Any]]],
        dict[str, list[dict[str, Any]]],
    ]:
        by_id: dict[int | None, list[dict[str, Any]]] = defaultdict(list)
        by_pc: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            proposal_id = optional_int(legacy_value(row, "propostaID"))
            pc = normalize_legacy_text(legacy_value(row, "PC"))
            if proposal_id is not None:
                by_id[proposal_id].append(row)
            if pc:
                by_pc[pc].append(row)
        return by_id, by_pc

    def _sync_proposal(self, row: dict[str, Any]) -> Proposal | None:
        legacy_id = optional_int(legacy_value(row, "propostaID"))
        code = repair_legacy_text(legacy_value(row, "PC"))[:20]
        entry_date = optional_date(legacy_value(row, "DataDeEntrada"))
        client_name = repair_legacy_text(legacy_value(row, "Cliente"))
        if not code or entry_date is None or not client_name:
            self.stats["proposals_skipped"] += 1
            return None

        party = self._resolve_party(row, client_name)
        division = self._resolve_division(legacy_value(row, "Divisao"))
        department = self._resolve_department(legacy_value(row, "propDepartamento"), division)
        if department is not None and department.division_id is not None:
            division = department.division
        type_name = legacy_value(row, "tipoProposta") or legacy_value(row, "propostaTipo")
        proposal_type = self._resolve_proposal_type(type_name)
        issuer = self._resolve_user(legacy_value(row, "Emitente"))
        technical = self._resolve_user(legacy_value(row, "tecnicoResponsavel"))

        key = legacy_key(
            "proposals",
            f"id:{legacy_id}" if legacy_id is not None else f"pc:{normalize_legacy_text(code)}",
        )
        proposal = self._proposals_by_legacy_key.get(key)
        if proposal is None and legacy_id is not None:
            proposal = self._proposals_by_legacy_id.get(legacy_id)
        if proposal is None:
            proposal = self._proposals_by_code.get(normalize_legacy_text(code))

        status = proposal_status(legacy_value(row, "Posicao"))
        values = {
            "origin": CatalogOrigin.LEGACY,
            "legacy_id": legacy_id,
            "legacy_key": key,
            "legacy_payload": row,
            "code": code,
            "party": party,
            "entry_date": entry_date,
            "division": division,
            "department": department,
            "work_name": (
                repair_legacy_text(
                    legacy_value(row, "Obra") or legacy_value(row, "Nome_Obra")
                )
                or code
            )[:180],
            "description": repair_legacy_text(legacy_value(row, "Descricao")),
            "execution_days": optional_int(legacy_value(row, "prazoDeEntrega")),
            "expected_delivery_date": optional_date(legacy_value(row, "dataDeEntrega")),
            "proposal_type": proposal_type,
            "technical_responsible": technical,
            "issuer": issuer,
            "status": status,
            "accepted_at": optional_datetime(legacy_value(row, "dataaprov")) if status == ProposalStatus.ACCEPTED else None,
            "contract_value": optional_decimal(legacy_value(row, "valorDoContrato"), Decimal("0")),
            "additional_value": optional_decimal(legacy_value(row, "valorAdicional"), Decimal("0")),
        }
        if proposal is None:
            proposal = Proposal.objects.create(**values)
            self.stats["proposals_created"] += 1
        else:
            for field, value in values.items():
                setattr(proposal, field, value)
            proposal.save()
            self.stats["proposals_updated"] += 1

        self._proposals_by_legacy_key[key] = proposal
        if legacy_id is not None:
            self._proposals_by_legacy_id[legacy_id] = proposal
        self._proposals_by_code[normalize_legacy_text(code)] = proposal

        if status == ProposalStatus.ACCEPTED and party.party_type == PartyType.INTERESTED:
            party.party_type = PartyType.CLIENT
            party.converted_at = values["accepted_at"]
            party.save(update_fields=("party_type", "converted_at", "updated_at"))
            self.stats["parties_converted"] += 1
        return proposal

    def _resolve_party(self, row: dict[str, Any], client_name: str) -> Party:
        client_id = optional_int(legacy_value(row, "clienteID"))
        party = (
            self._parties_by_legacy_id.get(client_id)
            if client_id is not None
            else None
        )
        normalized_name = normalize_legacy_text(client_name)
        if party is None:
            party = self._parties_by_name.get(normalized_name)
        if party is not None:
            return party

        key = legacy_key("proposal-parties", normalized_name)
        party, created = Party.objects.get_or_create(
            legacy_key=key,
            defaults={
                "origin": CatalogOrigin.LEGACY,
                "person_type": PersonType.COMPANY,
                "legal_name": client_name[:180],
                "legacy_payload": {
                    "source": "proposal",
                    "client_name": client_name,
                },
            },
        )
        self.stats["parties_created" if created else "parties_reused"] += 1
        if client_id is not None:
            self._parties_by_legacy_id[client_id] = party
        self._parties_by_name[normalized_name] = party
        return party

    def _resolve_department(
        self,
        value: object,
        division: Division | None,
    ) -> Department | None:
        name = repair_legacy_text(value)
        normalized = normalize_legacy_text(name)
        aliases = {"OBRAS": "OBRA"}
        normalized = aliases.get(normalized, normalized)
        if not normalized:
            return None
        department = self._departments.get(normalized)
        if department is not None:
            return department

        department = Department.objects.filter(name__iexact=name).first()
        if department is None and normalized != normalize_legacy_text(name):
            department = next(
                (
                    item
                    for item in Department.objects.filter(is_active=True)
                    if normalize_legacy_text(item.name) == normalized
                ),
                None,
            )
        if department is None:
            department = Department.objects.create(
                name=name[:150],
                division=division,
                origin=CatalogOrigin.LEGACY,
                legacy_key=legacy_key("proposal-departments", normalized),
            )
            self.stats["departments_created_from_proposals"] += 1
        self._departments[normalized] = department
        return department

    def _resolve_user(self, value: object):
        name = repair_legacy_text(value)
        if not name:
            return None
        normalized = normalize_legacy_text(name)
        if normalized in self._users:
            return self._users[normalized]
        User = get_user_model()
        query = Q(username__iexact=name)
        if any(field.name == "name" for field in User._meta.fields):
            query |= Q(name__iexact=name)
        user = User.objects.filter(query).order_by("id").first()
        self._users[normalized] = user
        return user

    def _sync_services(
        self,
        proposal: Proposal,
        rows: list[dict[str, Any]],
    ) -> None:
        if not rows and proposal.id not in self._service_proposal_ids:
            return

        received_keys: set[str] = set()
        for index, row in enumerate(rows, start=1):
            project_id = optional_int(legacy_value(row, "projetoID"))
            project_name = repair_legacy_text(legacy_value(row, "Projeto"))
            project = self._projects_by_id.get(project_id) if project_id is not None else None
            if project is None:
                project = self._projects_by_name.get(normalize_legacy_text(project_name))
            if project is None and project_name:
                project = Project.objects.create(
                    name=project_name[:150],
                    department=proposal.department,
                    origin=CatalogOrigin.LEGACY,
                    legacy_key=legacy_key("proposal-projects", normalize_legacy_text(project_name)),
                    legacy_payload=row,
                )
                self._projects_by_name[normalize_legacy_text(project_name)] = project
                self.stats["projects_created_from_services"] += 1
            if project is None:
                self.stats["services_skipped"] += 1
                continue

            identity = _row_identity(
                row,
                ("projetoPropostaID",),
                f"{proposal.legacy_key}|row:{index}|project:{project.id}",
            )
            key = legacy_key("proposal-requested-services", identity)
            received_keys.add(key)
            _, created = ProposalRequestedService.objects.update_or_create(
                legacy_key=key,
                defaults={
                    "proposal": proposal,
                    "project": project,
                    "area": optional_decimal(
                        legacy_value(row, "area"),
                        decimal_places=4,
                    ),
                    "proposed_value": optional_decimal(legacy_value(row, "valor_projeto")),
                    "contracted_value": optional_decimal(
                        legacy_value(row, "valor_projeto contratado")
                    ),
                    "position": repair_legacy_text(
                        legacy_value(row, "posicao_por_proj")
                        or legacy_value(row, "Posicao")
                    )[:80],
                    "completion_date": optional_date(
                        legacy_value(row, "conclusao_por_projeto")
                    ),
                    "sort_order": index,
                    "origin": CatalogOrigin.LEGACY,
                    "legacy_id": optional_int(legacy_value(row, "projetoPropostaID")),
                    "legacy_payload": row,
                },
            )
            self.stats["services_created" if created else "services_updated"] += 1
            self._service_proposal_ids.add(proposal.id)

        ProposalRequestedService.objects.filter(
            proposal=proposal,
            origin=CatalogOrigin.LEGACY,
        ).exclude(legacy_key__in=received_keys).delete()
        if not rows:
            self._service_proposal_ids.discard(proposal.id)

    def _sync_contacts(
        self,
        proposal: Proposal,
        proposal_row: dict[str, Any],
        relation_rows: list[dict[str, Any]],
    ) -> None:
        candidates: list[dict[str, Any]] = []
        for index in (1, 2):
            name = repair_legacy_text(legacy_value(proposal_row, f"Contato{index}P"))
            if name:
                candidates.append(
                    {
                        "name": name,
                        "position": repair_legacy_text(legacy_value(proposal_row, f"Cargo{index}P")),
                        "phone": repair_legacy_text(legacy_value(proposal_row, f"Fone{index}P")),
                        "mobile": repair_legacy_text(legacy_value(proposal_row, f"Celular{index}P")),
                        "email": repair_legacy_text(legacy_value(proposal_row, f"e-mail{index}P")),
                        "identity": f"embedded:{index}",
                        "payload": proposal_row,
                    }
                )

        for index, row in enumerate(relation_rows, start=1):
            name = repair_legacy_text(legacy_value(row, "contatoNome"))
            if name:
                candidates.append(
                    {
                        "name": name,
                        "position": "",
                        "phone": "",
                        "mobile": "",
                        "email": "",
                        "identity": _row_identity(
                            row,
                            ("contatoId", "contatoClienteId"),
                            f"relation:{index}",
                        ),
                        "payload": row,
                    }
                )

        deduplicated: dict[str, dict[str, Any]] = {}
        for candidate in candidates:
            candidate_key = normalize_legacy_text(candidate["name"])
            if candidate_key not in deduplicated:
                deduplicated[candidate_key] = candidate
                continue
            current = deduplicated[candidate_key]
            for field in ("position", "phone", "mobile", "email"):
                if not current[field] and candidate[field]:
                    current[field] = candidate[field]
        candidates = list(deduplicated.values())

        if not candidates and proposal.id not in self._contact_proposal_ids:
            return

        received_keys: set[str] = set()
        first_contact = None
        for index, candidate in enumerate(candidates, start=1):
            contact = Contact.objects.filter(
                party=proposal.party,
                name__iexact=candidate["name"],
            ).order_by("id").first()
            if contact is None:
                contact = Contact.objects.create(
                    party=proposal.party,
                    name=candidate["name"][:150],
                    position=candidate["position"][:120],
                    phone=candidate["phone"][:30],
                    mobile=candidate["mobile"][:30],
                    email=candidate["email"][:254],
                    is_primary=first_contact is None,
                )
                self.stats["contacts_created"] += 1
            if first_contact is None:
                first_contact = contact

            key = legacy_key(
                "proposal-contacts",
                f"{proposal.legacy_key}|{candidate['identity']}",
            )
            received_keys.add(key)
            _, created = ProposalContact.objects.update_or_create(
                legacy_key=key,
                defaults={
                    "proposal": proposal,
                    "contact": contact,
                    "context": ProposalContactContext.CLIENT,
                    "is_primary": index == 1,
                    "sort_order": index,
                    "origin": CatalogOrigin.LEGACY,
                    "legacy_payload": candidate["payload"],
                },
            )
            self.stats[
                "proposal_contacts_created" if created else "proposal_contacts_updated"
            ] += 1
            self._contact_proposal_ids.add(proposal.id)

        ProposalContact.objects.filter(
            proposal=proposal,
            origin=CatalogOrigin.LEGACY,
        ).exclude(legacy_key__in=received_keys).delete()
        if not candidates:
            self._contact_proposal_ids.discard(proposal.id)

        if first_contact is not None and proposal.requester_contact_id is None:
            proposal.requester_contact = first_contact
            proposal.save(update_fields=("requester_contact", "updated_at"))

    def _sync_installments(
        self,
        proposal: Proposal,
        rows: list[dict[str, Any]],
        *,
        source: str,
    ) -> None:
        if not rows and proposal.id not in self._installment_proposal_ids:
            return

        ProposalInstallment.objects.filter(proposal=proposal).exclude(
            source=InstallmentSource.HUB
        ).exclude(source=source).delete()

        received_keys: set[str] = set()
        id_column = "pppId" if source == InstallmentSource.LEGACY_INSTALLMENTS else "codigo_planpag"
        for index, row in enumerate(rows, start=1):
            amount_column = "pppValor" if source == InstallmentSource.LEGACY_INSTALLMENTS else "valor_parcela"
            due_column = "pppVencimento" if source == InstallmentSource.LEGACY_INSTALLMENTS else "data_prevista"
            status_column = "pppSituacao" if source == InstallmentSource.LEGACY_INSTALLMENTS else "status"
            label_column = "pppParcela" if source == InstallmentSource.LEGACY_INSTALLMENTS else "Parcela"
            amount = optional_decimal(legacy_value(row, amount_column))
            if amount is None:
                continue

            identity = _row_identity(
                row,
                (id_column,),
                f"{proposal.legacy_key}|{source}|row:{index}",
            )
            key = legacy_key(source, identity)
            received_keys.add(key)
            _, created = ProposalInstallment.objects.update_or_create(
                legacy_key=key,
                defaults={
                    "proposal": proposal,
                    "label": repair_legacy_text(legacy_value(row, label_column))[:30] or str(index),
                    "sequence": index,
                    "amount": amount,
                    "due_date": optional_date(legacy_value(row, due_column)),
                    "paid_at": optional_date(legacy_value(row, "data_real")),
                    "status": installment_status(legacy_value(row, status_column)),
                    "source": source,
                    "legacy_id": optional_int(legacy_value(row, id_column)),
                    "legacy_payload": row,
                },
            )
            self.stats[
                "installments_created" if created else "installments_updated"
            ] += 1
            self._installment_proposal_ids.add(proposal.id)

        ProposalInstallment.objects.filter(proposal=proposal).exclude(
            legacy_key__in=received_keys
        ).exclude(source=InstallmentSource.HUB).delete()
        if not rows:
            self._installment_proposal_ids.discard(proposal.id)
