import sys

from access_connection import get_access_connection


def main():
    if len(sys.argv) < 2:
        print("Uso: python legacy_reader/inspect_table.py NOME_DA_TABELA")
        return

    table_name = sys.argv[1]

    with get_access_connection() as connection:
        cursor = connection.cursor()

        print(f"Colunas de: {table_name}")
        print("-" * 80)

        for column in cursor.columns(table=table_name):
            print(
                f"{column.column_name} | "
                f"{column.type_name} | "
                f"size={column.column_size}"
            )

        print()
        print("Primeiros registros:")
        print("-" * 80)

        cursor.execute(f"SELECT TOP 10 * FROM [{table_name}]")
        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()

        print(" | ".join(columns))
        print("-" * 80)

        for row in rows:
            values = []
            for value in row:
                values.append(repr(value))
            print(" | ".join(values))


if __name__ == "__main__":
    main()