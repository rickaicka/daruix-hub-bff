import json
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings


class LegacyBridgeHttpError(Exception):
    """Falha de comunicação ou resposta inválida do Legacy Bridge."""


class LegacyBridgeClient:
    def __init__(self) -> None:
        self.base_url = settings.LEGACY_BRIDGE_URL.rstrip("/")
        self.token = settings.LEGACY_BRIDGE_TOKEN
        self.timeout = max(
            settings.LEGACY_BRIDGE_CONNECT_TIMEOUT,
            settings.LEGACY_BRIDGE_READ_TIMEOUT,
        )

        if not self.base_url:
            raise LegacyBridgeHttpError("LEGACY_BRIDGE_URL não configurado.")
        if not self.token:
            raise LegacyBridgeHttpError("LEGACY_BRIDGE_TOKEN não configurado.")

    def authenticate(self, username: str, password: str) -> dict:
        return self._request(
            "POST",
            "/v1/authenticate",
            body={"username": username, "password": password},
        )

    def list_clients(self, search: str, limit: int) -> list[dict]:
        return self._request(
            "GET",
            "/v1/clients",
            query={"search": search, "limit": limit},
        )

    def list_works(
        self,
        client_name: str,
        client_document: str,
        search: str,
        limit: int,
    ) -> list[dict]:
        return self._request(
            "GET",
            "/v1/works",
            query={
                "client_name": client_name,
                "client_document": client_document,
                "search": search,
                "limit": limit,
            },
        )

    def get_work(self, work_id: int) -> dict | None:
        try:
            return self._request("GET", f"/v1/works/{work_id}")
        except LegacyBridgeHttpError as error:
            if getattr(error, "status_code", None) == 404:
                return None
            raise

    def _request(
        self,
        method: str,
        path: str,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if query:
            values = {
                key: value
                for key, value in query.items()
                if value not in (None, "")
            }
            if values:
                url = f"{url}?{urlencode(values)}"

        data = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url, data=data, headers=headers, method=method)

        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw_payload = response.read().decode("utf-8")
        except HTTPError as error:
            message = self._http_error_message(error)
            bridge_error = LegacyBridgeHttpError(message)
            bridge_error.status_code = error.code
            raise bridge_error from error
        except (URLError, TimeoutError, socket.timeout) as error:
            raise LegacyBridgeHttpError(
                "Não foi possível conectar ao Legacy Bridge."
            ) from error

        try:
            return json.loads(raw_payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise LegacyBridgeHttpError(
                "O Legacy Bridge retornou uma resposta inválida."
            ) from error

    @staticmethod
    def _http_error_message(error: HTTPError) -> str:
        try:
            payload = json.loads(error.read().decode("utf-8"))
            detail = payload.get("detail")
            if detail:
                return str(detail)
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            pass
        return f"Legacy Bridge respondeu com HTTP {error.code}."
