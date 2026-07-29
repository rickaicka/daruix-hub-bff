import argparse
import json
import re
import sys
from typing import Any

from access_connection import get_access_connection


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def normalize_display_text(value: Any) -> str:
    return " ".join(normalize_text(value).split())


def normalize_client_name(value: Any) -> str:
    return normalize_display_text(value).casefold()


def normalize_document(value: Any) -> str:
    return re.sub(r"\D", "", normalize_text(value))


def normalize_integer(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def print_json(payload: dict) -> None:
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
        )
    )


def build_client_payload(row) -> dict:
    return {
        "name": normalize_display_text(row.faturado),
        "document": normalize_text(row.cnpjfat),
    }


def build_work_payload(row) -> dict:
    delivery_contact = normalize_text(row.contatentrega)
    billing_contact = normalize_text(row.contfat)

    return {
        "legacy_work_id": normalize_integer(row.cod),
        "legacy_proposal_id": normalize_integer(row.propostaID),
        "cost_center": normalize_text(row.pc),
        "work_name": normalize_text(row.apelido),
        "client_name": normalize_text(row.faturado),
        "client_document": normalize_text(row.cnpjfat),
        "attention_to_suggestion": (
            delivery_contact or billing_contact
        ),
        "delivery_address": normalize_text(row.endentrega),
        "delivery_phone": normalize_text(row.foneentrega),
    }


def find_existing_client_index(
    clients: list[dict],
    indexes_by_name: dict[str, list[int]],
    index_by_document: dict[str, int],
    name_key: str,
    document_key: str,
) -> int | None:
    if document_key and document_key in index_by_document:
        return index_by_document[document_key]

    for index in indexes_by_name.get(name_key, []):
        existing_document_key = normalize_document(
            clients[index]["document"]
        )

        if (
            not document_key
            or not existing_document_key
            or document_key == existing_document_key
        ):
            return index

    return None


def list_clients(
    search: str = "",
    limit: int = 100,
) -> list[dict]:
    query = """
        SELECT DISTINCT
            faturado,
            cnpjfat
        FROM [Cadastro Obra]
        WHERE obraFinalizada = False
          AND faturado IS NOT NULL
          AND Trim(faturado) <> ''
    """

    parameters = []

    if search:
        query += """
            AND (
                faturado LIKE ?
                OR cnpjfat LIKE ?
            )
        """

        search_value = f"%{search}%"

        parameters.extend([
            search_value,
            search_value,
        ])

    query += """
        ORDER BY faturado
    """

    with get_access_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(query, parameters)

        rows = cursor.fetchall()

    clients = []
    indexes_by_name: dict[str, list[int]] = {}
    index_by_document: dict[str, int] = {}

    for row in rows:
        client = build_client_payload(row)
        name_key = normalize_client_name(client["name"])
        document_key = normalize_document(client["document"])

        existing_index = find_existing_client_index(
            clients=clients,
            indexes_by_name=indexes_by_name,
            index_by_document=index_by_document,
            name_key=name_key,
            document_key=document_key,
        )

        if existing_index is not None:
            existing_client = clients[existing_index]

            if (
                not normalize_document(existing_client["document"])
                and document_key
            ):
                existing_client["document"] = client["document"]
                index_by_document[document_key] = existing_index

            continue

        client_index = len(clients)
        clients.append(client)

        indexes_by_name.setdefault(name_key, []).append(client_index)

        if document_key:
            index_by_document[document_key] = client_index

        if len(clients) >= limit:
            break

    return clients


def work_belongs_to_client(
    work: dict,
    client_name: str,
    client_document: str,
) -> bool:
    requested_name = normalize_client_name(client_name)
    requested_document = normalize_document(client_document)

    if not requested_name and not requested_document:
        return True

    work_name = normalize_client_name(work["client_name"])
    work_document = normalize_document(work["client_document"])

    if requested_document and work_document:
        return requested_document == work_document

    if requested_name:
        return requested_name == work_name

    return False


def list_works(
    client_name: str = "",
    client_document: str = "",
    search: str = "",
    limit: int = 100,
) -> list[dict]:
    query = """
        SELECT
            cod,
            pc,
            propostaID,
            apelido,
            faturado,
            cnpjfat,
            contatentrega,
            contfat,
            endentrega,
            foneentrega
        FROM [Cadastro Obra]
        WHERE obraFinalizada = False
    """

    parameters = []

    if search:
        query += """
            AND (
                apelido LIKE ?
                OR pc LIKE ?
                OR faturado LIKE ?
            )
        """

        search_value = f"%{search}%"

        parameters.extend([
            search_value,
            search_value,
            search_value,
        ])

    query += """
        ORDER BY faturado, apelido
    """

    with get_access_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(query, parameters)

        rows = cursor.fetchall()

    works = []

    for row in rows:
        work = build_work_payload(row)

        if not work_belongs_to_client(
            work=work,
            client_name=client_name,
            client_document=client_document,
        ):
            continue

        works.append(work)

        if len(works) >= limit:
            break

    return works


def get_work(work_id: int) -> dict | None:
    query = """
        SELECT
            cod,
            pc,
            propostaID,
            apelido,
            faturado,
            cnpjfat,
            contatentrega,
            contfat,
            endentrega,
            foneentrega
        FROM [Cadastro Obra]
        WHERE cod = ?
          AND obraFinalizada = False
    """

    with get_access_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(query, work_id)

        row = cursor.fetchone()

    if not row:
        return None

    return build_work_payload(row)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bridge de leitura do Access para o módulo "
            "de Memorandos de Remessa."
        )
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    clients_parser = subparsers.add_parser(
        "list-clients",
        help="Lista clientes que possuem obras ativas.",
    )

    clients_parser.add_argument(
        "--search",
        default="",
    )

    clients_parser.add_argument(
        "--limit",
        type=int,
        default=100,
    )

    works_parser = subparsers.add_parser(
        "list-works",
        help="Lista obras ativas.",
    )

    works_parser.add_argument(
        "--client-name",
        default="",
    )

    works_parser.add_argument(
        "--client-document",
        default="",
    )

    works_parser.add_argument(
        "--search",
        default="",
    )

    works_parser.add_argument(
        "--limit",
        type=int,
        default=100,
    )

    work_parser = subparsers.add_parser(
        "get-work",
        help="Retorna uma obra ativa pelo código legado.",
    )

    work_parser.add_argument(
        "--work-id",
        type=int,
        required=True,
    )

    return parser


def normalize_limit(value: int) -> int:
    return max(
        1,
        min(value, 500),
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "list-clients":
            data = list_clients(
                search=normalize_text(args.search),
                limit=normalize_limit(args.limit),
            )

        elif args.command == "list-works":
            data = list_works(
                client_name=normalize_text(
                    args.client_name
                ),
                client_document=normalize_text(
                    args.client_document
                ),
                search=normalize_text(args.search),
                limit=normalize_limit(args.limit),
            )

        elif args.command == "get-work":
            data = get_work(args.work_id)

        else:
            raise ValueError(
                f"Comando não reconhecido: {args.command}"
            )

        print_json({
            "success": True,
            "data": data,
        })

    except Exception as error:
        print_json({
            "success": False,
            "error": str(error),
            "error_type": error.__class__.__name__,
        })

        sys.exit(1)


if __name__ == "__main__":
    main()