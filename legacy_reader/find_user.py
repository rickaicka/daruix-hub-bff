import sys
import pyodbc


DB_PATH = r"C:\SGO\SGO.accdb"
DRIVER = "Microsoft Access Driver (*.mdb, *.accdb)"


def main():
    search = sys.argv[1] if len(sys.argv) > 1 else ""

    conn = pyodbc.connect(
        f"DRIVER={{{DRIVER}}};"
        f"DBQ={DB_PATH};"
    )

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            usuarioID,
            usuNome,
            usuGrupo,
            usuNomeCompleto
        FROM tblUsuario
        WHERE usuNome LIKE ?
           OR usuNomeCompleto LIKE ?
        """,
        f"%{search}%",
        f"%{search}%",
    )

    rows = cursor.fetchall()

    if not rows:
        print("Nenhum usuário encontrado.")
    else:
        for row in rows:
            print({
                "usuarioID": row.usuarioID,
                "usuNome": row.usuNome,
                "usuGrupo": row.usuGrupo,
                "usuNomeCompleto": row.usuNomeCompleto,
            })

    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()