from access_connection import get_access_connection


def normalize(value):
    if value is None:
        return ""
    return str(value).strip().lower()


def main():
    username = input("Usuário para procurar: ").strip()
    username_normalized = normalize(username)

    with get_access_connection() as connection:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                usuarioID,
                usuNome,
                usuSenha,
                usuGrupo,
                usuNomeCompleto,
                usuPainel,
                usuDedutiveis
            FROM tblUsuario
        """)

        rows = cursor.fetchall()

    print("-" * 80)
    print(f"Procurando por: {username!r}")
    print("-" * 80)

    found = False

    for row in rows:
        usuario_id = row.usuarioID
        usu_nome = row.usuNome
        usu_senha = row.usuSenha
        usu_grupo = row.usuGrupo
        nome_completo = row.usuNomeCompleto
        painel = row.usuPainel
        dedutiveis = row.usuDedutiveis

        if username_normalized in normalize(usu_nome) or normalize(usu_nome) in username_normalized:
            found = True

            print(f"ID: {usuario_id}")
            print(f"usuNome repr: {usu_nome!r}")
            print(f"usuNome len: {len(str(usu_nome)) if usu_nome is not None else 0}")
            print(f"usuSenha repr: {usu_senha!r}")
            print(f"usuSenha len: {len(str(usu_senha)) if usu_senha is not None else 0}")
            print(f"usuGrupo repr: {usu_grupo!r}")
            print(f"usuNomeCompleto: {nome_completo!r}")
            print(f"usuPainel: {painel!r}")
            print(f"usuDedutiveis: {dedutiveis!r}")
            print("-" * 80)

    if not found:
        print("Nenhum usuário parecido encontrado.")

        print("\nPrimeiros usuários encontrados:")
        for row in rows[:20]:
            print(
                f"ID={row.usuarioID} | "
                f"usuNome={row.usuNome!r} | "
                f"grupo={row.usuGrupo!r} | "
                f"nome={row.usuNomeCompleto!r}"
            )


if __name__ == "__main__":
    main()