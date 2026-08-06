import os

import pywintypes
import win32com.client


database_path = os.environ.get(
    "LEGACY_DATABASE_PATH",
    r"C:\SGO\SGO.accdb",
)

target = os.environ.get(
    "LEGACY_REFERENCE_TARGET",
    "ItemDaComposicaoDeServico",
)

normalized_target = target.casefold()


def get_com_error_message(exc: pywintypes.com_error) -> str:
    try:
        details = exc.args[2]

        if details and len(details) > 2 and details[2]:
            return str(details[2])
    except Exception:
        pass

    return str(exc)


engine = win32com.client.Dispatch("DAO.DBEngine.120")
database = engine.OpenDatabase(database_path)

found = []
skipped = []

try:
    print(f"Banco aberto: {database.Name}")
    print(f"Referência procurada: {target}")
    print("-" * 80)

    for query in database.QueryDefs:
        query_name = str(query.Name)

        try:
            sql = str(query.SQL or "")
        except pywintypes.com_error as exc:
            skipped.append(
                (
                    query_name,
                    get_com_error_message(exc),
                )
            )
            continue

        if normalized_target not in sql.casefold():
            continue

        found.append(query_name)

        try:
            query_type = query.Type
        except pywintypes.com_error:
            query_type = "indisponível"

        print(f"\nConsulta: {query_name!r}")
        print(f"Type: {query_type}")
        print("-" * 80)
        print(sql)

    print("\n" + "=" * 80)
    print(f"Total de consultas encontradas: {len(found)}")

    if skipped:
        print(
            "\nConsultas ignoradas porque o Access "
            "não conseguiu interpretar o SQL:"
        )

        for query_name, message in skipped:
            print(f"\n- {query_name!r}")
            print(f"  {message}")

        print(f"\nTotal de consultas ignoradas: {len(skipped)}")
    else:
        print("\nNenhuma consulta precisou ser ignorada.")

finally:
    database.Close()