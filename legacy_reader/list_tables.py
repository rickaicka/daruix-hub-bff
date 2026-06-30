from access_connection import get_access_connection


def main():
    with get_access_connection() as connection:
        cursor = connection.cursor()

        print("Tabelas encontradas:")
        print("-" * 80)

        for table in cursor.tables(tableType="TABLE"):
            print(table.table_name)


if __name__ == "__main__":
    main()