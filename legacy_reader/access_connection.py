import pyodbc
from decouple import config


ACCESS_DRIVER = "Microsoft Access Driver (*.mdb, *.accdb)"


def get_access_connection():
    db_path = config("LEGACY_DB_PATH", default=r"C:\SGO\SGO.accdb")

    connection_string = (
        f"DRIVER={{{ACCESS_DRIVER}}};"
        f"DBQ={db_path};"
    )

    return pyodbc.connect(connection_string)