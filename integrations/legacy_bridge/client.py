from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

PageRequestCallback = Callable[[str, int, int], None]
PageResponseCallback = Callable[[str, int, int, bool], None]


class LegacyBridgeHttpError(RuntimeError):
    """Falha de configuração, comunicação ou contrato do Legacy Bridge."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code


class LegacyBridgeClient:
    COMMERCIAL_RESOURCES = frozenset(
        {
            "proposals",
            "proposal-requested-services",
            "proposal-contacts",
            "proposal-payment-installments",
            "proposal-payment-plans",
            "proposal-types",
            "departments",
            "projects",
            "works",
        }
    )

    def __init__(self) -> None:
        self.base_url = settings.LEGACY_BRIDGE_URL.rstrip("/")
        self.token = settings.LEGACY_BRIDGE_TOKEN
        self.timeout = max(
            float(settings.LEGACY_BRIDGE_CONNECT_TIMEOUT),
            float(settings.LEGACY_BRIDGE_READ_TIMEOUT),
        )

        if not self.base_url:
            raise LegacyBridgeHttpError("LEGACY_BRIDGE_URL não configurado.")
        if not self.token:
            raise LegacyBridgeHttpError("LEGACY_BRIDGE_TOKEN não configurado.")
        if self.timeout <= 0:
            raise LegacyBridgeHttpError(
                "O timeout do Legacy Bridge deve ser maior que zero."
            )

    def authenticate(self, username: str, password: str) -> dict[str, Any]:
        payload = self._request(
            "POST",
            "/v1/authenticate",
            body={"username": username, "password": password},
        )
        return self._expect_dict(payload, "autenticação")

    def list_clients(self, search: str, limit: int) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            "/v1/clients",
            query={"search": search, "limit": limit},
        )
        return self._expect_list(payload, "clientes")

    def list_clients_catalog(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/v1/clients/catalog")
        return self._expect_list(payload, "catálogo de clientes")

    def list_business_segments(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/v1/business-segments")
        return self._expect_list(payload, "ramos empresariais")

    def list_company_types(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/v1/company-types")
        return self._expect_list(payload, "tipos de empresa")

    def list_budget_stage_catalog(self) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            "/v1/budgeting/stage-catalog",
        )
        return self._expect_list(
            payload,
            "catálogo de etapas de orçamento",
        )

    def list_works(
        self,
        client_name: str,
        client_document: str,
        search: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            "/v1/works",
            query={
                "client_name": client_name,
                "client_document": client_document,
                "search": search,
                "limit": limit,
            },
        )
        return self._expect_list(payload, "obras")

    def get_work(self, work_id: int) -> dict[str, Any] | None:
        try:
            payload = self._request("GET", f"/v1/works/{work_id}")
        except LegacyBridgeHttpError as error:
            if error.status_code == 404:
                return None
            raise

        return self._expect_dict(payload, "obra")

    def iter_budgeting_resource(
        self,
        resource: str,
        *,
        page_size: int = 500,
        on_page_request: PageRequestCallback | None = None,
        on_page_response: PageResponseCallback | None = None,
    ) -> Iterator[dict[str, Any]]:
        yield from self._iter_paged_resource(
            path=f"/v1/budgeting/{resource}",
            resource=resource,
            page_size=page_size,
            on_page_request=on_page_request,
            on_page_response=on_page_response,
        )

    def iter_commercial_resource(
        self,
        resource: str,
        *,
        page_size: int = 500,
        search: str = "",
        filter_column: str = "",
        filter_value: object = "",
        on_page_request: PageRequestCallback | None = None,
        on_page_response: PageResponseCallback | None = None,
    ) -> Iterator[dict[str, Any]]:
        if resource not in self.COMMERCIAL_RESOURCES:
            raise ValueError(f"Recurso comercial não permitido: {resource}.")

        if bool(filter_column) != (filter_value not in (None, "")):
            raise ValueError(
                "filter_column e filter_value devem ser informados juntos."
            )

        yield from self._iter_paged_resource(
            path=f"/v1/commercial/{resource}",
            resource=resource,
            page_size=page_size,
            extra_query={
                "search": search,
                "filter_column": filter_column,
                "filter_value": filter_value,
            },
            on_page_request=on_page_request,
            on_page_response=on_page_response,
        )

    def _iter_paged_resource(
        self,
        *,
        path: str,
        resource: str,
        page_size: int,
        extra_query: dict[str, Any] | None = None,
        on_page_request: PageRequestCallback | None = None,
        on_page_response: PageResponseCallback | None = None,
    ) -> Iterator[dict[str, Any]]:
        if page_size < 1:
            raise ValueError("page_size deve ser maior que zero.")

        offset = 0
        visited_offsets: set[int] = set()

        while True:
            if offset in visited_offsets:
                raise LegacyBridgeHttpError(
                    f"Paginação circular detectada em {resource}."
                )
            visited_offsets.add(offset)

            if on_page_request:
                on_page_request(resource, offset, page_size)

            payload = self._request(
                "GET",
                path,
                query={
                    "offset": offset,
                    "limit": page_size,
                    **(extra_query or {}),
                },
            )
            page = self._expect_dict(payload, resource)
            items = self._expect_list(page.get("items"), resource)
            has_more = bool(page.get("has_more"))

            if on_page_response:
                on_page_response(
                    resource,
                    offset,
                    len(items),
                    has_more,
                )

            yield from items

            if not has_more:
                return
            if not items and page.get("next_offset") is None:
                raise LegacyBridgeHttpError(f"Paginação de {resource} não avançou.")

            raw_next_offset = page.get("next_offset")
            try:
                next_offset = int(
                    raw_next_offset
                    if raw_next_offset is not None
                    else offset + len(items)
                )
            except (TypeError, ValueError) as error:
                raise LegacyBridgeHttpError(
                    f"Paginação inválida em {resource}."
                ) from error

            if next_offset <= offset:
                raise LegacyBridgeHttpError(
                    f"Paginação inválida em {resource}: next_offset={next_offset}."
                )
            offset = next_offset

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
                key: value for key, value in query.items() if value not in (None, "")
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
            raise LegacyBridgeHttpError(
                self._http_error_message(error),
                status_code=error.code,
            ) from error
        except (URLError, TimeoutError) as error:
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
    def _expect_dict(payload: Any, resource: str) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise LegacyBridgeHttpError(
                f"O Legacy Bridge retornou {resource} em formato inválido."
            )
        return payload

    @staticmethod
    def _expect_list(payload: Any, resource: str) -> list[dict[str, Any]]:
        if not isinstance(payload, list) or not all(
            isinstance(item, dict) for item in payload
        ):
            raise LegacyBridgeHttpError(
                f"O Legacy Bridge retornou {resource} em formato inválido."
            )
        return payload

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
