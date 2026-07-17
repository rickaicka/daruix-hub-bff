import argparse
import json
import sys
from typing import Any

from access_connection import get_access_connection


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


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
        "name": normalize_text(row.faturado),
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
    seen_clients = set()

    for row in rows:
        client = build_client_payload(row)

        key = (
            client["name"].casefold(),
            client["document"],
        )

        if key in seen_clients:
            continue

        seen_clients.add(key)
        clients.append(client)

        if len(clients) >= limit:
            break

    return clients


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

    if client_name:
        query += """
            AND faturado = ?
        """
        parameters.append(client_name)

    if client_document:
        query += """
            AND cnpjfat = ?
        """
        parameters.append(client_document)

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

    return [
        build_work_payload(row)
        for row in rows[:limit]
    ]


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