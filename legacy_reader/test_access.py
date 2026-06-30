import pyodbc


DB_PATH = r"C:\SGO\SGO.accdb"
DRIVER = "Microsoft Access Driver (*.mdb, *.accdb)"


def main():
    conn = pyodbc.connect(
        f"DRIVER={{{DRIVER}}};"
        f"DBQ={DB_PATH};"
    )

    cursor = conn.cursor()

    print("Tabelas encontradas:")
    print("-" * 40)

    for table in cursor.tables(tableType="TABLE"):
        print(table.table_name)

    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()