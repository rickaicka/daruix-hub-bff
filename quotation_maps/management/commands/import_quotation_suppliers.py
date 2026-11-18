import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quotation_maps.models import Supplier


class Command(BaseCommand):
    help = "Importa fornecedores usando a tabela e as colunas confirmadas no Access."
    optional_fields = ("document", "contact", "phone", "email", "fax", "address", "notes", "trade_name",
                       "business_segment", "website", "payment_terms", "delivery_terms")
    sgo_table = "Cadastro  Fornecedores"
    sgo_fields = {
        "name": "RazaoSocial", "document": "CNPJ", "contact": "Contato1F", "phone": "Telefone",
        "email": "Email", "fax": "Fax", "notes": "Observações dos ContatosF",
        "trade_name": "nome fantasia", "business_segment": "Ramo Empresarial", "website": "Site",
        "payment_terms": "CondiçõesDoPagamento", "delivery_terms": "Prazo de Entrega",
    }
    sgo_address = ("Endereço", "Bairro", "Cidade", "Estado", "CEP")

    def add_arguments(self, parser):
        parser.add_argument("export", type=Path)
        parser.add_argument("--sgo", action="store_true", help="Usa o mapeamento do cadastro principal do SGO.")
        parser.add_argument("--table")
        parser.add_argument("--id", action="append", dest="identity")
        parser.add_argument("--name")
        for field in self.optional_fields:
            parser.add_argument(f"--{field}")
        parser.add_argument("--apply", action="store_true")

    @transaction.atomic
    def handle(self, **options):
        sgo = options["sgo"]
        table_name = options["table"] or (self.sgo_table if sgo else None)
        if not table_name or not (sgo or options["name"]):
            raise CommandError("Use --sgo ou informe --table e --name.")
        try:
            table = json.loads(options["export"].read_text(encoding="utf-8"))["tables"][table_name]
            rows = table["rows"]
            identity = options["identity"] or table["primary_key"]
            columns = {column["name"] for column in table["columns"]}
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise CommandError("Exportação ou tabela inválida.") from error
        if not identity:
            raise CommandError("Informe uma chave estável com --id.")
        mapping = self.sgo_fields.copy() if sgo else {}
        mapping.update({field: options[field] for field in ("name", *self.optional_fields) if options[field]})
        required = set(identity).union(mapping.values())
        if sgo:
            required.update((*self.sgo_address, "bloqueado"))
        if missing := required.difference(columns):
            raise CommandError(f"Colunas não encontradas: {', '.join(sorted(missing))}")
        suppliers = {}
        for number, row in enumerate(rows, 1):
            key_values = [row.get(col) for col in identity]
            if any(value is None or str(value).strip() == "" for value in key_values):
                raise CommandError(f"Chave ausente na linha {number}.")
            key = json.dumps([table_name, *key_values], ensure_ascii=False, separators=(",", ":"))
            if key in suppliers or len(key) > 255:
                raise CommandError(f"Chave duplicada ou longa demais na linha {number}.")
            fields = {field: str(row[col]).strip() if row.get(col) is not None else "" for field, col in mapping.items()}
            if sgo:
                fields["name"] = fields["name"] or fields["trade_name"]
                fields["email"] = fields["email"] or str(row.get("e-mail1f") or "").strip()
                fields["phone"] = fields["phone"] or str(row.get("Tel1f") or row.get("Cel1f") or "").strip()
                if not options["address"]:
                    fields["address"] = ", ".join(str(row[col]).strip() for col in self.sgo_address if row.get(col))
                fields["active"] = str(row["bloqueado"]).strip().lower() not in {"true", "1", "-1", "sim"}
            if not fields["name"]:
                raise CommandError(f"Nome ausente na linha {number}.")
            suppliers[key] = dict(fields, source=row)
        if options["apply"]:
            for key, fields in suppliers.items():
                Supplier.objects.update_or_create(source_key=key, defaults=fields)
        mode = "Importados" if options["apply"] else "Validados em simulação"
        self.stdout.write(f"{mode}: {len(suppliers)} fornecedores.")
