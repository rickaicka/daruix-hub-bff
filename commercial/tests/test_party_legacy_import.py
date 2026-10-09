from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from commercial.models import CatalogOrigin, Party, PartyType, PersonType


@override_settings(
    LEGACY_BRIDGE_URL="http://legacy-bridge:8100",
    LEGACY_BRIDGE_TOKEN="test-token",
)
class PartyLegacyImportTest(TestCase):
    @patch(
        "commercial.management.commands."
        "import_legacy_commercial_catalogs.LegacyBridgeClient"
    )
    def test_imports_clients_into_local_party_base(self, client_class):
        client = client_class.return_value
        client.list_business_segments.return_value = []
        client.list_company_types.return_value = []
        client.list_clients_catalog.return_value = [
            {
                "name": "Cliente Legado Ltda.",
                "document": "12.345.678/0001-90",
                "legacy_key": "a" * 64,
            }
        ]

        # O import deve aceitar fixtures antigas sem legacy_id, pois
        # legacy_key continua sendo uma identidade válida de sincronização.
        call_command("import_legacy_commercial_catalogs")

        party = Party.objects.get(legacy_key="a" * 64)
        self.assertEqual(party.origin, CatalogOrigin.LEGACY)
        self.assertEqual(party.party_type, PartyType.CLIENT)
        self.assertEqual(party.person_type, PersonType.COMPANY)
        self.assertEqual(party.legal_name, "Cliente Legado Ltda.")
        self.assertEqual(party.document, "12.345.678/0001-90")
        self.assertIsNone(party.legacy_id)

    @patch(
        "commercial.management.commands."
        "import_legacy_commercial_catalogs.LegacyBridgeClient"
    )
    def test_reimport_updates_instead_of_duplicating(self, client_class):
        client = client_class.return_value
        client.list_business_segments.return_value = []
        client.list_company_types.return_value = []
        client.list_clients_catalog.return_value = [
            {
                "name": "Cliente A",
                "document": "123",
                "legacy_key": "b" * 64,
            }
        ]

        call_command("import_legacy_commercial_catalogs")
        call_command("import_legacy_commercial_catalogs")

        self.assertEqual(
            Party.objects.filter(legacy_key="b" * 64).count(),
            1,
        )

    @patch(
        "commercial.management.commands."
        "import_legacy_commercial_catalogs.LegacyBridgeClient"
    )
    def test_missing_legacy_client_is_deactivated(self, client_class):
        Party.objects.create(
            origin=CatalogOrigin.LEGACY,
            legacy_key="c" * 64,
            party_type=PartyType.CLIENT,
            person_type=PersonType.COMPANY,
            legal_name="Cliente Antigo",
        )

        client = client_class.return_value
        client.list_business_segments.return_value = []
        client.list_company_types.return_value = []
        client.list_clients_catalog.return_value = []

        call_command("import_legacy_commercial_catalogs")

        party = Party.objects.get(legacy_key="c" * 64)
        self.assertFalse(party.is_active)
