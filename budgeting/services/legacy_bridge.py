from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from integrations.legacy_bridge import (
    LegacyBridgeClient,
    LegacyBridgeHttpError,
    PageRequestCallback,
    PageResponseCallback,
)


class LegacyBridgeError(RuntimeError):
    """Erro do Legacy Bridge exposto ao domínio de orçamentos."""


class LegacyBudgetingClient:
    def __init__(
        self,
        *,
        on_page_request: PageRequestCallback | None = None,
        on_page_response: PageResponseCallback | None = None,
    ) -> None:
        self.client = LegacyBridgeClient()
        self.on_page_request = on_page_request
        self.on_page_response = on_page_response

    def iter_resource(
        self,
        resource: str,
        page_size: int = 500,
    ) -> Iterator[dict[str, Any]]:
        try:
            yield from self.client.iter_budgeting_resource(
                resource,
                page_size=page_size,
                on_page_request=self.on_page_request,
                on_page_response=self.on_page_response,
            )
        except LegacyBridgeHttpError as error:
            raise LegacyBridgeError(str(error)) from error

    def list_stage_catalog(self) -> list[dict[str, Any]]:
        resource = "stage-catalog"

        try:
            if self.on_page_request:
                self.on_page_request(resource, 0, 500)

            items = self.client.list_budget_stage_catalog()

            if self.on_page_response:
                self.on_page_response(
                    resource,
                    0,
                    len(items),
                    False,
                )

            return items
        except LegacyBridgeHttpError as error:
            raise LegacyBridgeError(str(error)) from error
