"""Cliente interno de leitura de RM. Não é um endpoint público do Hub."""
from __future__ import annotations

import json
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

RESOURCES = frozenset({"requests", "request-items"})


class LegacyRequisitionError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class LegacyMaterialRequisitionClient:
    def __init__(self, *, base_url: str, token: str, timeout: float = 15, opener=None):
        parts = urlsplit(base_url)
        if (parts.scheme not in {"http", "https"} or not parts.netloc
                or parts.username or parts.password or parts.query or parts.fragment):
            raise ValueError("URL do bridge inválida.")
        if not token or "\n" in token or "\r" in token or timeout <= 0:
            raise ValueError("Token ou timeout do bridge inválido.")
        self.base_url = base_url.rstrip("/")
        self._token = token
        self.timeout = timeout
        self._opener = opener or build_opener(_NoRedirect())

    @classmethod
    def from_django_settings(cls):
        from django.conf import settings
        if getattr(settings, "LEGACY_BRIDGE_MODE", "http") != "http":
            raise ValueError("A conexão de RM requer LEGACY_BRIDGE_MODE=http.")
        return cls(base_url=settings.LEGACY_BRIDGE_URL,
                   token=settings.LEGACY_BRIDGE_TOKEN,
                   timeout=float(getattr(settings, "LEGACY_BRIDGE_READ_TIMEOUT", 15)))

    def _get(self, path, params=None):
        url = self.base_url + "/v1/material-requisitions/" + path
        if params:
            url += "?" + urlencode(params)
        request = Request(url, headers={"Authorization": "Bearer " + self._token,
                                        "Accept": "application/json"}, method="GET")
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                return json.load(response)
        except HTTPError as error:
            # Não vazar corpo do legado, credenciais ou endereços internos.
            raise LegacyRequisitionError("Falha HTTP na leitura de RM no bridge.",
                                         status_code=error.code) from None
        except (URLError, TimeoutError, socket.timeout, OSError):
            raise LegacyRequisitionError("Bridge indisponível para leitura de RM.") from None
        except (ValueError, UnicodeError):
            raise LegacyRequisitionError("Resposta JSON inválida do bridge.") from None

    def list_tables(self):
        data = self._get("tables")
        if not isinstance(data, list) or any(not isinstance(x, dict) for x in data):
            raise LegacyRequisitionError("Catálogo de RM inválido.")
        return data

    def iter_resource(self, resource, *, page_size=500, search="",
                      filter_column="", filter_value=""):
        if resource not in RESOURCES:
            raise ValueError("Recurso de RM não permitido.")
        if type(page_size) is not int or not 1 <= page_size <= 500:
            raise ValueError("page_size deve estar entre 1 e 500.")
        if bool(filter_column.strip()) != bool(filter_value.strip()):
            raise ValueError("Filtro exige coluna e valor.")
        offset = 0
        while True:
            params = {"offset": offset, "limit": page_size, "search": search.strip()}
            if filter_column.strip():
                params.update(filter_column=filter_column.strip(),
                              filter_value=filter_value.strip())
            page = self._get(resource, params)
            if not isinstance(page, dict):
                raise LegacyRequisitionError("Página de RM inválida.")
            items = page.get("items")
            more = page.get("has_more")
            next_offset = page.get("next_offset")
            if (page.get("resource") != resource or page.get("offset") != offset
                    or page.get("limit") != page_size or not isinstance(items, list)
                    or len(items) > page_size or any(not isinstance(x, dict) for x in items)
                    or type(more) is not bool
                    or (more and (not items or type(next_offset) is not int
                                  or next_offset != offset + len(items)))
                    or (not more and next_offset is not None)):
                raise LegacyRequisitionError("Contrato de paginação de RM inválido.")
            yield from items
            if not more:
                return
            offset = next_offset
