import json
import os
import subprocess
from pathlib import Path
from typing import Any

from django.conf import settings


class LegacyBridgeError(Exception):
    pass


def _validate_file_path(
    path_value: str | Path,
    description: str,
) -> Path:
    path = Path(path_value)

    if not path.exists():
        raise LegacyBridgeError(
            f"{description} não encontrado: {path}"
        )

    if not path.is_file():
        raise LegacyBridgeError(
            f"{description} não é um arquivo válido: {path}"
        )

    return path


def _build_environment() -> dict[str, str]:
    environment = os.environ.copy()

    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"

    return environment


def _run_bridge(arguments: list[str]) -> Any:
    python_path = _validate_file_path(
        settings.LEGACY_PYTHON_PATH,
        "Executável Python legado",
    )

    bridge_path = _validate_file_path(
        settings.LEGACY_MEMORANDO_REMESSAS_BRIDGE_PATH,
        "Bridge de Memorandos de Remessa",
    )

    command = [
        str(python_path),
        str(bridge_path),
        *arguments,
    ]

    try:
        result = subprocess.run(
            command,
            cwd=str(settings.BASE_DIR),
            env=_build_environment(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=settings.LEGACY_BRIDGE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise LegacyBridgeError(
            "A consulta ao banco legado excedeu o tempo limite."
        ) from error
    except OSError as error:
        raise LegacyBridgeError(
            "Não foi possível executar o bridge do banco legado."
        ) from error

    output = result.stdout.strip()
    error_output = result.stderr.strip()

    if not output:
        message = (
            error_output
            or "O bridge legado não retornou nenhuma resposta."
        )

        raise LegacyBridgeError(message)

    try:
        payload = json.loads(output)
    except json.JSONDecodeError as error:
        raise LegacyBridgeError(
            "O bridge legado retornou uma resposta inválida."
        ) from error

    if result.returncode != 0 or not payload.get("success"):
        message = (
            payload.get("error")
            or error_output
            or "Erro não identificado no bridge legado."
        )

        raise LegacyBridgeError(message)

    return payload.get("data")


def _normalize_limit(limit: int) -> int:
    return max(
        1,
        min(int(limit), 500),
    )


def list_legacy_clients(
    search: str = "",
    limit: int = 100,
) -> list[dict]:
    arguments = [
        "list-clients",
        "--limit",
        str(_normalize_limit(limit)),
    ]

    search = str(search or "").strip()

    if search:
        arguments.extend([
            "--search",
            search,
        ])

    data = _run_bridge(arguments)

    return data or []


def list_legacy_works(
    client_name: str = "",
    client_document: str = "",
    search: str = "",
    limit: int = 100,
) -> list[dict]:
    arguments = [
        "list-works",
        "--limit",
        str(_normalize_limit(limit)),
    ]

    client_name = str(client_name or "").strip()
    client_document = str(client_document or "").strip()
    search = str(search or "").strip()

    if client_name:
        arguments.extend([
            "--client-name",
            client_name,
        ])

    if client_document:
        arguments.extend([
            "--client-document",
            client_document,
        ])

    if search:
        arguments.extend([
            "--search",
            search,
        ])

    data = _run_bridge(arguments)

    return data or []


def get_legacy_work(
    legacy_work_id: int,
) -> dict | None:
    try:
        normalized_id = int(legacy_work_id)
    except (TypeError, ValueError) as error:
        raise LegacyBridgeError(
            "O ID legado da obra é inválido."
        ) from error

    if normalized_id <= 0:
        raise LegacyBridgeError(
            "O ID legado da obra deve ser maior que zero."
        )

    return _run_bridge([
        "get-work",
        "--work-id",
        str(normalized_id),
    ])