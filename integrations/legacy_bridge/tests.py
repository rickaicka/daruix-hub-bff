import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from accounts.legacy.legacy_auth_client import LegacyAuthClient
from memorando_remessas.services.legacy_service import (
    get_legacy_work,
    list_legacy_clients,
    list_legacy_works,
)


SETTINGS = {
    "LEGACY_AUTH_ENABLED": True,
    "LEGACY_BRIDGE_MODE": "http",
    "LEGACY_BRIDGE_URL": "http://legacy-bridge:8100",
    "LEGACY_BRIDGE_TOKEN": "test-token",
    "LEGACY_BRIDGE_CONNECT_TIMEOUT": 1,
    "LEGACY_BRIDGE_READ_TIMEOUT": 2,
}


def response(payload):
    mocked = MagicMock()
    mocked.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return mocked


@override_settings(**SETTINGS)
class LegacyBridgeHttpIntegrationTests(SimpleTestCase):
    @patch("integrations.legacy_bridge.client.urlopen")
    def test_authentication_uses_http_without_password_in_url(self, urlopen):
        urlopen.return_value = response({"authenticated": True, "legacy_user": {}})

        payload = LegacyAuthClient().authenticate("ricardo", "secret")

        request = urlopen.call_args.args[0]
        self.assertTrue(payload["authenticated"])
        self.assertEqual(request.full_url, "http://legacy-bridge:8100/v1/authenticate")
        self.assertEqual(json.loads(request.data), {"username": "ricardo", "password": "secret"})
        self.assertEqual(request.headers["Authorization"], "Bearer test-token")

    @patch("integrations.legacy_bridge.client.urlopen")
    def test_clients_and_works_keep_existing_service_contract(self, urlopen):
        urlopen.side_effect = [
            response([{"name": "Cliente A", "document": "123"}]),
            response([{"legacy_work_id": 575, "work_name": "Obra A"}]),
            response({"legacy_work_id": 575, "work_name": "Obra A"}),
        ]

        self.assertEqual(list_legacy_clients(limit=10)[0]["name"], "Cliente A")
        self.assertEqual(list_legacy_works(client_name="Cliente A")[0]["legacy_work_id"], 575)
        self.assertEqual(get_legacy_work(575)["work_name"], "Obra A")
