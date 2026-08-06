from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings


class LegacyBridgeError(RuntimeError):
    pass


class LegacyBudgetingClient:
    def __init__(
        self,
        *,
        on_page_request: Callable[[str, int, int], None] | None = None,
        on_page_response: Callable[[str, int, int, bool], None] | None = None,
    ) -> None:
        self.base_url = settings.LEGACY_BRIDGE_URL.rstrip("/")
        self.token = settings.LEGACY_BRIDGE_TOKEN
        self.timeout = float(settings.LEGACY_BRIDGE_READ_TIMEOUT)
        self.on_page_request = on_page_request
        self.on_page_response = on_page_response

    def iter_resource(self, resource: str, page_size: int = 500) -> Iterator[dict[str, Any]]:
        offset = 0
        while True:
            if self.on_page_request:
                self.on_page_request(resource, offset, page_size)
            page = self._get(
                f"/v1/budgeting/{resource}",
                params={"offset": offset, "limit": page_size},
            )
            items = page.get("items")
            if not isinstance(items, list):
                raise LegacyBridgeError(f"Resposta de {resource} sem a lista 'items'.")
            has_more = bool(page.get("has_more"))
            if self.on_page_response:
                self.on_page_response(resource, offset, len(items), has_more)
            for item in items:
                if not isinstance(item, dict):
                    raise LegacyBridgeError(f"Resposta de {resource} contém item inválido.")
                yield item
            if not has_more:
                break
            next_offset = page.get("next_offset")
            offset = int(next_offset if next_offset is not None else offset + len(items))

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}?{urlencode(params)}"
        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise LegacyBridgeError("Falha ao consultar o Legacy Bridge.") from error
        if not isinstance(payload, dict):
            raise LegacyBridgeError("O Legacy Bridge devolveu um contrato inválido.")
        return payload
