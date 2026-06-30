from access_connection import get_access_connection


KEYWORDS = [
    "acesso",
    "access",
    "permiss",
    "permission",
    "perfil",
    "profile",
    "grupo",
    "group",
    "usuario",
    "usuário",
    "user",
    "menu",
    "salvar",
    "save",
    "excluir",
    "delete",
    "alterar",
    "update",
    "editar",
    "edit",
    "incluir",
    "insert",
    "criar",
    "create",
    "consultar",
    "visualizar",
    "view",
    "bloqueio",
    "libera",
    "senha",
    "login",
    "status",
]


def normalize(value):
    if value is None:
        return ""

    return str(value).strip().lower()


def contains_keyword(value):
    value = normalize(value)

    return any(keyword in value for keyword in KEYWORDS)


def get_table_names(cursor):
    table_names = []

    for table in cursor.tables():
        table_name = table.table_name

        if not table_name:
            continue

        if str(table_name).startswith("MSys"):
            continue

        table_names.append(table_name)

    return table_names


def get_columns_by_select(cursor, table_name):
    try:
        cursor.execute(f"SELECT TOP 1 * FROM [{table_name}]")
        return [column[0] for column in cursor.description or []]
    except Exception as error:
        return [f"ERRO_AO_LER_COLUNAS: {error}"]


def main():
    with get_access_connection() as connection:
        cursor = connection.cursor()

        table_names = get_table_names(cursor)

        print("Procurando tabelas/colunas relacionadas a acesso/permissão...")
        print("-" * 100)

        found_any = False

        for table_name in table_names:
            table_match = contains_keyword(table_name)
            columns = get_columns_by_select(cursor, table_name)

            matched_columns = [
                column_name
                for column_name in columns
                if contains_keyword(column_name)
            ]

            if table_match or matched_columns:
                found_any = True

                print(f"Tabela: {table_name}")

                if table_match:
                    print("  - nome da tabela parece relacionado")

                if matched_columns:
                    print("  - colunas suspeitas:")
                    for column_name in matched_columns:
                        print(f"    - {column_name}")

                print("-" * 100)

        if not found_any:
            print("Nenhuma tabela/coluna suspeita encontrada.")


if __name__ == "__main__":
    main()