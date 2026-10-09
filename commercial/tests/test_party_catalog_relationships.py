from types import SimpleNamespace

from django.test import TestCase
from rest_framework.test import APIClient

from commercial.models import (
    BusinessSegment,
    CatalogOrigin,
    CompanyType,
    Party,
    PersonType,
)
from commercial.serializers import PartySerializer


class PartyCatalogRelationshipsTest(TestCase):
    def setUp(self):
        self.segment = BusinessSegment.objects.create(
            name="Instalações elétricas",
            origin=CatalogOrigin.LEGACY,
            legacy_key="a" * 64,
        )
        self.company_type = CompanyType.objects.create(
            name="Cliente",
            origin=CatalogOrigin.LEGACY,
            legacy_key="b" * 64,
        )

        # Os endpoints comerciais são protegidos por autenticação global.
        # APIClient.force_authenticate evita acoplar este teste ao modelo
        # concreto de usuário do projeto, já que aqui testamos somente GET.
        self.client = APIClient()
        self.client.force_authenticate(
            user=SimpleNamespace(is_authenticated=True)
        )

    def test_creates_company_party_using_local_catalog_primary_keys(self):
        serializer = PartySerializer(
            data={
                "person_type": PersonType.COMPANY,
                "legal_name": "Cliente Teste Ltda.",
                "business_segment": self.segment.pk,
                "company_type": self.company_type.pk,
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        party = serializer.save()

        self.assertEqual(party.business_segment_id, self.segment.pk)
        self.assertEqual(party.company_type_id, self.company_type.pk)
        self.assertEqual(serializer.data["business_segment"], self.segment.pk)
        self.assertEqual(serializer.data["company_type"], self.company_type.pk)
        self.assertEqual(
            serializer.data["business_segment_name"],
            self.segment.name,
        )

    def test_rejects_inactive_catalog_primary_key(self):
        self.segment.is_active = False
        self.segment.save(update_fields=("is_active",))

        serializer = PartySerializer(
            data={
                "person_type": PersonType.COMPANY,
                "legal_name": "Cliente Teste Ltda.",
                "business_segment": self.segment.pk,
                "company_type": self.company_type.pk,
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("business_segment", serializer.errors)

    def test_rejects_company_catalogs_for_individual_party(self):
        serializer = PartySerializer(
            data={
                "person_type": PersonType.INDIVIDUAL,
                "legal_name": "Cliente Pessoa Física",
                "business_segment": self.segment.pk,
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("person_type", serializer.errors)

    def test_clients_endpoint_uses_local_party_base(self):
        Party.objects.create(
            party_type="CLIENT",
            person_type=PersonType.COMPANY,
            legal_name="Cliente Local Ltda.",
            document="12.345.678/0001-90",
        )
        Party.objects.create(
            party_type="INTERESTED",
            person_type=PersonType.COMPANY,
            legal_name="Interessado Local Ltda.",
        )

        response = self.client.get(
            "/api/commercial/parties/clients/?search=Cliente"
        )

        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(
            payload["results"][0]["legal_name"],
            "Cliente Local Ltda.",
        )
