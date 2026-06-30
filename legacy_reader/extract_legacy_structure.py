import json
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal

from access_connection import get_access_connection


IGNORED_MENU_COLUMNS = {
    "cod",
    "código",
    "codigo",
    "id",
}


def json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return str(value)

    return str(value)


def normalize_text(value):
    if value is None:
        return ""

    return str(value).strip()


def normalize_slug(value):
    value = normalize_text(value).lower()

    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")

    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = value.strip("_")

    return value or "default"


def fetch_groups(cursor):
    cursor.execute(
        """
        SELECT DISTINCT usuGrupo
        FROM [T_Usuario]
        WHERE usuGrupo IS NOT NULL
        ORDER BY usuGrupo
        """
    )

    groups = []

    for row in cursor.fetchall():
        group_name = normalize_text(row.usuGrupo)

        if not group_name:
            continue

        groups.append(
            {
                "slug": normalize_slug(group_name),
                "name": group_name,
                "legacy_name": group_name,
            }
        )

    return groups


def fetch_users(cursor):
    cursor.execute(
        """
        SELECT
            usuNome,
            usuGrupo,
            usuAlcada,
            usuNomeCompleto,
            usuPainel,
            usuDedutiveis,
            usuLogado,
            usuLogadoEm
        FROM [T_Usuario]
        ORDER BY usuNome
        """
    )

    users = []

    columns = [column[0] for column in cursor.description]

    for row in cursor.fetchall():
        item = {}

        for index, column in enumerate(columns):
            item[column] = row[index]

        users.append(item)

    return users


def table_exists(cursor, table_name):
    for table in cursor.tables(tableType="TABLE"):
        if table.table_name.lower() == table_name.lower():
            return True

    return False


def fetch_menu_modules_from_columns(cursor, table_name):
    if not table_exists(cursor, table_name):
        return []

    modules = []

    try:
        columns = list(cursor.columns(table=table_name))
    except UnicodeDecodeError:
        print(f"Não foi possível ler colunas de {table_name} por UnicodeDecodeError.")
        return []

    for column in columns:
        column_name = normalize_text(column.column_name)

        if not column_name:
            continue

        if normalize_slug(column_name) in IGNORED_MENU_COLUMNS:
            continue

        modules.append(
            {
                "source_table": table_name,
                "slug": normalize_slug(column_name),
                "name": column_name,
                "legacy_name": column_name,
            }
        )

    return modules


def main():
    with get_access_connection() as connection:
        cursor = connection.cursor()

        groups = fetch_groups(cursor)
        users = fetch_users(cursor)

        modules = []
        modules.extend(fetch_menu_modules_from_columns(cursor, "Menu2"))
        modules.extend(fetch_menu_modules_from_columns(cursor, "MENU OBRAS"))

        unique_modules = {}

        for module in modules:
            unique_modules[module["slug"]] = module

        data = {
            "user_type": {
                "slug": "employee",
                "name": "Colaborador",
            },
            "groups": groups,
            "modules": list(unique_modules.values()),
            "users": users,
        }

    output_path = "legacy_reader/legacy_structure.json"

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
            default=json_default,
        )

    print(f"Exportado para: {output_path}")
    print(f"Grupos encontrados: {len(groups)}")
    print(f"Módulos encontrados: {len(unique_modules)}")
    print(f"Usuários encontrados: {len(users)}")


if __name__ == "__main__":
    main()