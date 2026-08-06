import json
import subprocess

from django.conf import settings
from integrations.legacy_bridge import LegacyBridgeClient, LegacyBridgeHttpError


class LegacyAuthError(Exception):
    pass


class LegacyAuthClient:
    """
    Cliente usado pelo Django 64 bits para chamar o bridge Python 32 bits.

    O Django não lê o Access diretamente.
    Ele executa:
    .venv32/Scripts/python.exe legacy_reader/auth_bridge.py --username ... --password ...
    """

    def authenticate(self, username, password):
        if not settings.LEGACY_AUTH_ENABLED:
            return None

        if settings.LEGACY_BRIDGE_MODE == "http":
            try:
                payload = LegacyBridgeClient().authenticate(username, password)
            except LegacyBridgeHttpError as error:
                raise LegacyAuthError(str(error)) from error

            return payload if payload.get("authenticated") else None

        if not settings.LEGACY_PYTHON_PATH:
            raise LegacyAuthError("LEGACY_PYTHON_PATH não configurado.")

        if not settings.LEGACY_AUTH_BRIDGE_PATH:
            raise LegacyAuthError("LEGACY_AUTH_BRIDGE_PATH não configurado.")

        command = [
            settings.LEGACY_PYTHON_PATH,
            settings.LEGACY_AUTH_BRIDGE_PATH,
            "--username",
            username,
            "--password",
            password,
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise LegacyAuthError("Timeout ao consultar o Access.") from error

        if result.returncode != 0:
            raise LegacyAuthError(
                f"Erro no bridge Access: {result.stderr.strip()}"
            )

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise LegacyAuthError(
                f"Resposta inválida do bridge Access: {result.stdout}"
            ) from error

        if not payload.get("authenticated"):
            return None

        return payload
