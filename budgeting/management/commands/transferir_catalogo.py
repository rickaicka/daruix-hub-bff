import json
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction

from budgeting.models import (
    MaterialGroup,
    ServiceComposition,
    ServiceCompositionGroup,
    ServiceCompositionItem,
    ServiceCompositionVersion,
    Supply,
    UnitMeasure,
)


MODELS = {
    "unidades": UnitMeasure,
    "grupos_insumo": MaterialGroup,
    "grupos_composicao": ServiceCompositionGroup,
    "insumos": Supply,
    "composicoes": ServiceComposition,
    "versoes": ServiceCompositionVersion,
    "itens": ServiceCompositionItem,
}

REFERENCES = {
    "grupos_composicao": {"parent_id": "grupos_composicao"},
    "insumos": {"unit_measure_id": "unidades", "material_group_id": "grupos_insumo"},
    "composicoes": {"group_id": "grupos_composicao"},
    "versoes": {"composition_id": "composicoes"},
    "itens": {
        "version_id": "versoes",
        "supply_id": "insumos",
        "subcomposition_id": "composicoes",
    },
}

KEYS = {
    "unidades": ("legacy_id",),
    "grupos_insumo": ("legacy_id", "nome"),
    "grupos_composicao": ("parent_id", "code"),
    "insumos": ("origin", "description", "supply_type", "unit", "unit_measure_id"),
    "composicoes": ("origin", "code", "name", "group_id"),
    "versoes": ("composition_id", "number"),
    "itens": ("version_id", "position"),
}

FORMAT = "daruix-catalogo-1"


def fields(model):
    return [
        field for field in model._meta.concrete_fields
        if not field.primary_key
        and not getattr(field, "auto_now", False)
        and not getattr(field, "auto_now_add", False)
        and field.attname not in {"created_by_id", "updated_by_id"}
    ]


def row_data(obj):
    return {field.attname: getattr(obj, field.attname) for field in fields(type(obj))}


def json_value(value):
    # Decimal precisa conservar todas as casas. Datetimes mantêm o fuso.
    from datetime import datetime
    from decimal import Decimal

    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Tipo sem representação no catálogo: {type(value).__name__}")


def identity(section, data, occurrences):
    if data.get("legacy_id") is not None:
        if section in {"insumos", "composicoes"}:
            return ("legado", data["origin"], data["legacy_table"], data["legacy_id"])
        if section == "itens":
            return ("legado", data["legacy_table"], data["legacy_id"])
    key = tuple(data[field] for field in KEYS[section])
    if section == "itens":
        # Há versões com mais de um componente na mesma posição.
        occurrences[key] += 1
        return ("posicao", *key, occurrences[key])
    return key


def ordered_groups(rows):
    pending = dict(rows)
    emitted = set()
    while pending:
        ready = [
            pk for pk, data in pending.items()
            if data["parent_id"] is None or data["parent_id"] in emitted
        ]
        if not ready:
            raise CommandError("A hierarquia de grupos contém um ciclo ou um pai ausente.")
        for pk in ready:
            yield pk, pending.pop(pk)
            emitted.add(pk)


def decode(payload):
    if not isinstance(payload, dict) or payload.get("format") != FORMAT:
        raise CommandError("Formato de catálogo incompatível.")
    sections = payload.get("catalogo")
    if not isinstance(sections, dict) or sections.keys() != MODELS.keys():
        raise CommandError("O arquivo não contém as seções esperadas.")

    decoded = {}
    for section, model in MODELS.items():
        model_fields = fields(model)
        expected = {field.attname for field in model_fields}
        rows = sections[section]
        if not isinstance(rows, list):
            raise CommandError(f"{section}: esperada uma lista de registros.")
        result = {}
        for row in rows:
            if not isinstance(row, dict):
                raise CommandError(f"{section}: registro inválido.")
            pk = row.get("pk")
            if type(pk) is not int or pk <= 0 or pk in result:
                raise CommandError(f"{section}: ID de origem inválido ou duplicado.")
            values = row.get("fields")
            if not isinstance(values, dict) or values.keys() != expected:
                raise CommandError(f"{section}: campos incompatíveis com o BFF atual.")
            result[pk] = {
                field.attname: field.to_python(values[field.attname])
                for field in model_fields
            }
        decoded[section] = result
    return decoded


class Command(BaseCommand):
    help = "Exporta/importa o catálogo de insumos e composições entre bases do Hub."

    def add_arguments(self, parser):
        parser.add_argument("operacao", choices=("exportar", "importar"))
        parser.add_argument("arquivo", type=Path)
        parser.add_argument("--aplicar", action="store_true", help="Confirma a gravação da importação.")
        parser.add_argument(
            "--sincronizar-itens", action="store_true",
            help="Permite remover itens excedentes somente das versões presentes no arquivo.",
        )

    def handle(self, *args, **options):
        path = options["arquivo"]
        try:
            if options["operacao"] == "exportar":
                if options["aplicar"] or options["sincronizar_itens"]:
                    raise CommandError("As opções de importação não se aplicam à exportação.")
                self.export(path)
                return
            with path.open(encoding="utf-8") as source:
                rows = decode(json.load(source))
            self.import_catalog(rows, options["aplicar"], options["sincronizar_itens"])
            if options["aplicar"]:
                self.stdout.write(self.style.SUCCESS("Catálogo importado."))
            else:
                self.stdout.write("Simulação concluída. Alterações revertidas.")
        except (OSError, ValueError, ValidationError, DatabaseError) as error:
            raise CommandError(str(error)) from error

    def export(self, path):
        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            catalog = {
                section: [
                    {"pk": obj.pk, "fields": row_data(obj)}
                    for obj in model.objects.order_by("pk").iterator()
                ]
                for section, model in MODELS.items()
            }
        with path.open("x", encoding="utf-8") as output:
            json.dump({"format": FORMAT, "catalogo": catalog}, output,
                      ensure_ascii=False, default=json_value)
        for section, rows in catalog.items():
            self.stdout.write(f"{section}: {len(rows)}")
        self.stdout.write(f"Exportado: {path}")

    @transaction.atomic
    def import_catalog(self, rows, apply, sync_items):
        if connection.vendor == "postgresql":
            tables = ", ".join(
                connection.ops.quote_name(table)
                for table in sorted(model._meta.db_table for model in MODELS.values())
            )
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '5s'")
                cursor.execute(f"LOCK TABLE {tables} IN SHARE ROW EXCLUSIVE MODE")

        mappings = {}
        for section, model in MODELS.items():
            mappings[section] = self.merge_section(section, model, rows[section], mappings, sync_items)
        if not apply:
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            transaction.set_rollback(True)

    def merge_section(self, section, model, rows, mappings, sync_items):
        ordering = ("position", "pk") if section == "itens" else ("pk",)
        occurrences = Counter()
        target = defaultdict(list)
        existing = list(model.objects.order_by(*ordering))
        for obj in existing:
            target[identity(section, row_data(obj), occurrences)].append(obj)

        mapping = {}
        mappings[section] = mapping
        source_keys = set()
        source_occurrences = Counter()
        changes = []
        creates = []
        counts = Counter()
        iterable = rows.items()
        if section == "grupos_composicao":
            iterable = ordered_groups(iterable)
        elif section == "itens":
            iterable = sorted(iterable, key=lambda pair: (pair[1]["position"], pair[0]))

        for source_pk, raw in iterable:
            data = raw.copy()
            for field, related_section in REFERENCES.get(section, {}).items():
                if data[field] is not None:
                    related_pk = mappings[related_section].get(data[field])
                    if related_pk is None:
                        raise CommandError(f"{section} #{source_pk}: referência ausente em {field}.")
                    data[field] = related_pk
            key = identity(section, data, source_occurrences)
            if key in source_keys or len(target[key]) > 1:
                raise CommandError(f"{section} #{source_pk}: identidade ambígua {key!r}.")
            source_keys.add(key)

            if not target[key]:
                obj = model(**data)
                if section == "grupos_composicao":
                    # O ID do grupo é necessário antes de importar seus filhos.
                    obj.save(force_insert=True)
                    mapping[source_pk] = obj.pk
                else:
                    creates.append((source_pk, obj))
                counts["criados"] += 1
                continue

            obj = target[key][0]
            mapping[source_pk] = obj.pk
            if row_data(obj) == data:
                counts["iguais"] += 1
                continue
            if section == "itens" and obj.version_id != data["version_id"]:
                raise CommandError(
                    f"Item legado #{obj.pk} está associado a outra versão no destino."
                )
            for field, value in data.items():
                setattr(obj, field, value)
            changes.append(obj)
            counts["atualizados"] += 1

        matched = set(mapping.values())
        extra = [obj for obj in existing if obj.pk not in matched]
        if section == "itens":
            imported_versions = set(mappings["versoes"].values())
            stale = [obj.pk for obj in extra if obj.version_id in imported_versions]
            if stale and not sync_items:
                raise CommandError(
                    f"{len(stale)} itens existem apenas no destino dentro das versões importadas "
                    f"(IDs iniciais: {stale[:10]}). Revise e repita com --sincronizar-itens "
                    "se o conteúdo da origem deve prevalecer nessas versões."
                )
            if stale:
                model.objects.filter(pk__in=stale).delete()
                counts["itens removidos"] = len(stale)
            counts["só no destino, preservados"] = len(extra) - len(stale)
        else:
            counts["só no destino, preservados"] = len(extra)

        if creates:
            objects = [obj for _, obj in creates]
            if connection.features.can_return_rows_from_bulk_insert:
                model.objects.bulk_create(objects, batch_size=500)
            else:
                for obj in objects:
                    obj.save(force_insert=True)
            mapping.update({source_pk: obj.pk for source_pk, obj in creates})
        if changes:
            model.objects.bulk_update(
                changes, [field.name for field in fields(model)], batch_size=250,
            )
        if section == "itens":
            expected = defaultdict(list)
            for source_pk, raw in iterable:
                expected[(raw["version_id"], raw["position"])].append(mapping[source_pk])
            for key, item_ids in expected.items():
                if item_ids != sorted(item_ids):
                    raise CommandError(
                        f"A versão de origem #{key[0]} tem itens na posição {key[1]} "
                        "cuja ordem de desempate é diferente no destino."
                    )
        if section == "versoes":
            imported_latest = {}
            for obj in existing:
                if obj.pk in matched:
                    imported_latest[obj.composition_id] = max(
                        obj.number, imported_latest.get(obj.composition_id, 0),
                    )
            for _, obj in creates:
                imported_latest[obj.composition_id] = max(
                    obj.number, imported_latest.get(obj.composition_id, 0),
                )
            counts["versões mais novas só no destino"] = sum(
                obj.number > imported_latest.get(obj.composition_id, obj.number)
                for obj in extra
            )
        self.stdout.write(f"{section}: " + ", ".join(f"{name}={count}" for name, count in sorted(counts.items())))
        return mapping
