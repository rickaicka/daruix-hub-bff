import argparse
import json
from datetime import date, datetime
from decimal import Decimal

from access_connection import get_access_connection


def json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return str(value)

    return str(value)


def print_json(payload):
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            default=json_default,
        )
    )


def fetch_user_by_username(username):
    with get_access_connection() as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                usuNome,
                usuSenha,
                usuNomeCompleto,
                usuLogado,
                usuLogadoEm
            FROM [T_Usuario]
            WHERE LCase(Trim(usuNome)) = LCase(Trim(?))
            """,
            username,
        )

        return cursor.fetchone()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    username = str(args.username or "").strip()
    password = str(args.password or "").strip()

    row = fetch_user_by_username(username)

    if not row:
        print_json(
            {
                "authenticated": False,
                "detail": "Usuário não encontrado no Access.",
            }
        )
        return

    access_password = str(row.usuSenha or "").strip()

    if access_password != password:
        print_json(
            {
                "authenticated": False,
                "detail": "Senha inválida no Access.",
            }
        )
        return

    legacy_username = str(row.usuNome or "").strip()
    full_name = str(row.usuNomeCompleto or "").strip() or legacy_username

    print_json(
        {
            "authenticated": True,
            "legacy_user": {
                "username": legacy_username,
                "legacy_username": legacy_username,
                "full_name": full_name,
                "email": None,
                "last_legacy_login_at": row.usuLogadoEm,
            },
            "groups": [],
            "modules": [],
            "permissions": [],
        }
    )


if __name__ == "__main__":
    main()