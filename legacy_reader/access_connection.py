from pathlib import Path

import pyodbc
from decouple import AutoConfig


ACCESS_DRIVER = "Microsoft Access Driver (*.mdb, *.accdb)"

# access_connection.py está em:
# <projeto>/legacy_reader/access_connection.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Faz o bridge procurar o .env sempre a partir da raiz do projeto,
# independentemente do diretório em que o subprocesso foi iniciado.
config = AutoConfig(search_path=str(PROJECT_ROOT))


def get_legacy_database_path() -> Path:
    configured_path = config(
        "LEGACY_DB_PATH",
        default=r"C:\SGO\SGO.accdb",
    )

    normalized_path = (
        str(configured_path)
        .strip()
        .strip('"')
        .strip("'")
    )

    database_path = Path(normalized_path)

    if not database_path.is_absolute():
        database_path = PROJECT_ROOT / database_path

    database_path = database_path.resolve()

    if not database_path.exists():
        raise FileNotFoundError(
            "O banco Access legado não foi encontrado em: "
            f"{database_path}"
        )

    if not database_path.is_file():
        raise FileNotFoundError(
            "O caminho configurado em LEGACY_DB_PATH não é um arquivo: "
            f"{database_path}"
        )

    return database_path


def get_access_connection() -> pyodbc.Connection:
    installed_drivers = pyodbc.drivers()

    if ACCESS_DRIVER not in installed_drivers:
        raise RuntimeError(
            "O driver do Microsoft Access não está instalado para esta "
            "arquitetura do Python. "
            f"Driver esperado: {ACCESS_DRIVER}. "
            f"Drivers encontrados: {installed_drivers}"
        )

    database_path = get_legacy_database_path()

    connection_string = (
        f"DRIVER={{{ACCESS_DRIVER}}};"
        f"DBQ={database_path};"
        "READONLY=1;"
    )

    return pyodbc.connect(
        connection_string,
        timeout=10,
    )