import pyodbc


DB_PATH = r"C:\SGO\SGO.accdb"
DRIVER = "Microsoft Access Driver (*.mdb, *.accdb)"
TABLE_NAME = "tblUsuario"


def main():
    conn = pyodbc.connect(
        f"DRIVER={{{DRIVER}}};"
        f"DBQ={DB_PATH};"
    )

    cursor = conn.cursor()

    cursor.execute(f"SELECT TOP 5 * FROM {TABLE_NAME}")

    columns = [column[0] for column in cursor.description]

    print("Colunas:")
    print(columns)
    print("-" * 80)

    for row in cursor.fetchall():
        row_dict = dict(zip(columns, row))

        # Evita printar senha inteira se existir algum campo com nome parecido
        safe_row = {}

        for key, value in row_dict.items():
            key_lower = key.lower()

            if "senha" in key_lower or "password" in key_lower:
                safe_row[key] = "***OCULTO***"
            else:
                safe_row[key] = value

        print(safe_row)

    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()