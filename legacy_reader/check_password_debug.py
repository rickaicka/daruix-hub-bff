import argparse

from access_connection import get_access_connection


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    username = str(args.username or "").strip()
    password = str(args.password or "").strip()

    with get_access_connection() as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                usuarioID,
                usuNome,
                usuSenha,
                usuGrupo,
                usuNomeCompleto
            FROM tblUsuario
            WHERE LCase(Trim(usuNome)) = LCase(Trim(?))
            """,
            username,
        )

        row = cursor.fetchone()

    if not row:
        print("Usuário não encontrado.")
        return

    access_password_raw = row.usuSenha
    access_password = str(access_password_raw or "").strip()

    print("-" * 60)
    print(f"Usuário Access: {row.usuNome!r}")
    print(f"Grupo: {row.usuGrupo!r}")
    print(f"Nome completo: {row.usuNomeCompleto!r}")
    print("-" * 60)
    print(f"Senha digitada tamanho: {len(password)}")
    print(f"Senha Access tamanho bruto: {len(str(access_password_raw or ''))}")
    print(f"Senha Access tamanho com strip: {len(access_password)}")
    print(f"Senha bate exatamente? {access_password == password}")
    print(f"Senha bate ignorando espaços? {access_password.strip() == password.strip()}")
    print("-" * 60)

    if access_password != password:
        print("Diferença por posição:")
        max_length = max(len(access_password), len(password))

        for index in range(max_length):
            access_char = access_password[index] if index < len(access_password) else None
            input_char = password[index] if index < len(password) else None

            same = access_char == input_char

            print(
                f"posição {index}: "
                f"access_ord={ord(access_char) if access_char else None} | "
                f"input_ord={ord(input_char) if input_char else None} | "
                f"igual={same}"
            )


if __name__ == "__main__":
    main()