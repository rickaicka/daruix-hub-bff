import getpass
import pyodbc


DB_PATH = r"C:\SGO\SGO.accdb"
DRIVER = "Microsoft Access Driver (*.mdb, *.accdb)"


def main():
    username = input("Usuário Access: ").strip()

    confirm = input(
        f"Confirmar exibição da senha do usuário '{username}'? digite SIM: "
    ).strip()

    if confirm != "SIM":
        print("Cancelado.")
        return

    conn = pyodbc.connect(
        f"DRIVER={{{DRIVER}}};"
        f"DBQ={DB_PATH};"
    )

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                usuarioID,
                usuNome,
                usuSenha,
                usuGrupo,
                usuNomeCompleto
            FROM tblUsuario
            WHERE usuNome = ?
            """,
            username,
        )

        row = cursor.fetchone()

        if not row:
            print("Usuário não encontrado.")
            return

        print("-" * 50)
        print(f"ID: {row.usuarioID}")
        print(f"Usuário: {row.usuNome}")
        print(f"Nome: {row.usuNomeCompleto}")
        print(f"Grupo: {row.usuGrupo}")
        print(f"Senha: {row.usuSenha}")
        print("-" * 50)

    finally:
        conn.close()


if __name__ == "__main__":
    main()