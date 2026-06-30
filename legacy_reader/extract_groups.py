from access_connection import get_access_connection


def main():
    with get_access_connection() as connection:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT DISTINCT usuGrupo
            FROM [T_Usuario]
            WHERE usuGrupo IS NOT NULL
            ORDER BY usuGrupo
        """)

        rows = cursor.fetchall()

    print("Grupos encontrados:")
    print("-" * 80)

    for row in rows:
        print(row.usuGrupo)


if __name__ == "__main__":
    main()