import os
import sys

import win32com.client
import pywintypes


database_path = os.environ.get(
    "LEGACY_DATABASE_PATH",
    r"C:\SGO\SGO_be.accdb",
)


def normalize(value: str) -> str:
    return value.strip().casefold()


if len(sys.argv) != 2:
    print("Uso:")
    print('python legacy_reader\\inspect_query.py "NomeDaConsulta"')
    raise SystemExit(1)


requested_name = sys.argv[1]
normalized_name = normalize(requested_name)

engine = win32com.client.Dispatch("DAO.DBEngine.120")
database = engine.OpenDatabase(database_path)

ado_connection = None
found = False

try:
    print(f"Banco aberto: {database.Name}")
    print(f"Objeto procurado: {requested_name!r}")

    # 1. Consulta local DAO
    for query_def in database.QueryDefs:
        if normalize(query_def.Name) == normalized_name:
            found = True

            print("\nEncontrado em DAO.QueryDefs")
            print(f"Nome real: {query_def.Name!r}")
            print("-" * 80)
            print(query_def.SQL)
            break

    # 2. Tabela ou objeto vinculado DAO
    if not found:
        for table_def in database.TableDefs:
            if normalize(table_def.Name) == normalized_name:
                found = True

                print("\nEncontrado em DAO.TableDefs")
                print(f"Nome real: {table_def.Name!r}")
                print(f"Attributes: {table_def.Attributes}")
                print(f"Connect: {table_def.Connect!r}")
                print(f"SourceTableName: {table_def.SourceTableName!r}")

                if table_def.Connect:
                    print(
                        "\nConclusão: é um objeto vinculado, "
                        "não uma consulta local do banco aberto."
                    )
                break

    # 3. View exposta pelo provedor ACE
    if not found:
        try:
            ado_connection = win32com.client.Dispatch("ADODB.Connection")
            ado_connection.Open(
                "Provider=Microsoft.ACE.OLEDB.12.0;"
                f"Data Source={database_path};"
            )

            catalog = win32com.client.Dispatch("ADOX.Catalog")
            catalog.ActiveConnection = ado_connection

            for view in catalog.Views:
                if normalize(view.Name) == normalized_name:
                    found = True

                    print("\nEncontrado em ADOX.Views")
                    print(f"Nome real: {view.Name!r}")
                    print("-" * 80)
                    print(view.Command.CommandText)
                    break

        except pywintypes.com_error as exc:
            print("\nADOX não conseguiu inspecionar as views:")
            print(exc)

    if not found:
        print("\nObjeto não encontrado em:")
        print("- DAO.QueryDefs")
        print("- DAO.TableDefs")
        print("- ADOX.Views")

        print("\nQueryDefs relacionadas disponíveis neste banco:")

        related_count = 0

        for query_def in database.QueryDefs:
            name = query_def.Name

            if any(
                term in normalize(name)
                for term in ("compos", "planilha", "insumo")
            ):
                related_count += 1
                print(repr(name))

        print(f"\nTotal relacionado: {related_count}")

finally:
    if ado_connection is not None:
        try:
            ado_connection.Close()
        except Exception:
            pass

    database.Close()