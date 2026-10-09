from django.test import TestCase

from commercial.models import (
    BusinessSegment,
    CatalogOrigin,
    CompanyType,
    Contact,
    Party,
    PartyType,
    PersonType,
)
from commercial.serializers import ClientFullSerializer
from commercial.services.parties import update_client_full


class ClientFullValidationTest(TestCase):
    def setUp(self):
        self.segment = BusinessSegment.objects.create(
            name="Serviços",
            origin=CatalogOrigin.HUB,
            is_active=True,
        )
        self.company_type = CompanyType.objects.create(
            name="Jurídica",
            origin=CatalogOrigin.HUB,
            is_active=True,
        )

    def valid_payload(self, **overrides):
        payload = {
            "person_type": PersonType.COMPANY,
            "legal_name": "Empresa Teste Ltda.",
            "document": "11.222.333/0001-81",
            "business_segment": self.segment.pk,
            "company_type": self.company_type.pk,
            "trade_name": "",
            "state_registration": "",
            "last_service": "",
            "referred_by": "",
            "website": "",
            "notes": "",
            "addresses": [
                {
                    "label": "Principal",
                    "postal_code": "04121-000",
                    "street": "Rua Santa Cruz",
                    "number": "541",
                    "complement": "",
                    "district": "Vila Mariana",
                    "city": "São Paulo",
                    "state": "SP",
                    "is_primary": True,
                    "is_active": True,
                }
            ],
            "contacts": [
                {
                    "name": "Contato principal",
                    "position": "",
                    "phone": "(11) 3083-3391",
                    "mobile": "(11) 99999-9999",
                    "email": "cliente@example.com",
                    "is_primary": True,
                    "is_active": True,
                }
            ],
        }
        payload.update(overrides)
        return payload

    def assert_field_required(self, field, value=None):
        payload = self.valid_payload()
        if value is None:
            payload.pop(field, None)
        else:
            payload[field] = value

        serializer = ClientFullSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn(field, serializer.errors)

    def test_accepts_complete_company_payload(self):
        serializer = ClientFullSerializer(data=self.valid_payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["document"], "11222333000181")
        self.assertEqual(
            serializer.validated_data["addresses"][0]["postal_code"],
            "04121000",
        )
        self.assertEqual(
            serializer.validated_data["contacts"][0]["phone"],
            "1130833391",
        )

    def test_requires_client_name(self):
        self.assert_field_required("legal_name", "")

    def test_requires_business_segment(self):
        self.assert_field_required("business_segment")

    def test_requires_company_type(self):
        self.assert_field_required("company_type")

    def test_requires_document(self):
        self.assert_field_required("document", "")

    def test_requires_address_list(self):
        self.assert_field_required("addresses")

    def test_requires_contact_list(self):
        self.assert_field_required("contacts")

    def test_requires_all_address_fields_except_complement(self):
        required_fields = (
            "postal_code",
            "street",
            "number",
            "district",
            "city",
            "state",
        )

        for field in required_fields:
            with self.subTest(field=field):
                payload = self.valid_payload()
                payload["addresses"][0][field] = ""
                serializer = ClientFullSerializer(data=payload)
                self.assertFalse(serializer.is_valid())
                self.assertIn("addresses", serializer.errors)

        payload = self.valid_payload()
        payload["addresses"][0]["complement"] = ""
        serializer = ClientFullSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_requires_phone_mobile_and_email(self):
        for field in ("phone", "mobile", "email"):
            with self.subTest(field=field):
                payload = self.valid_payload()
                payload["contacts"][0][field] = ""
                serializer = ClientFullSerializer(data=payload)
                self.assertFalse(serializer.is_valid())
                self.assertIn("contacts", serializer.errors)

    def test_rejects_invalid_email(self):
        payload = self.valid_payload()
        payload["contacts"][0]["email"] = "email-invalido"
        serializer = ClientFullSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn("contacts", serializer.errors)

    def test_rejects_invalid_postal_code(self):
        payload = self.valid_payload()
        payload["addresses"][0]["postal_code"] = "123"
        serializer = ClientFullSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn("addresses", serializer.errors)

    def test_rejects_invalid_phone(self):
        payload = self.valid_payload()
        payload["contacts"][0]["phone"] = "123"
        serializer = ClientFullSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn("contacts", serializer.errors)

    def test_rejects_invalid_mobile(self):
        payload = self.valid_payload()
        payload["contacts"][0]["mobile"] = "(11) 88888-9999"
        serializer = ClientFullSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn("contacts", serializer.errors)

    def test_update_response_includes_new_contact_after_prefetch(self):
        party = Party.objects.create(
            party_type=PartyType.CLIENT,
            person_type=PersonType.COMPANY,
            legal_name="Empresa com contatos",
            document="11222333000181",
            business_segment=self.segment,
            company_type=self.company_type,
        )
        primary = Contact.objects.create(
            party=party,
            name="Contato principal",
            phone="1130833391",
            mobile="11999999999",
            email="principal@example.com",
            is_primary=True,
            is_active=True,
        )

        # Reproduz o get_object() do ViewSet, que traz a relação em cache.
        party = (
            Party.objects
            .prefetch_related("contacts")
            .get(pk=party.pk)
        )
        list(party.contacts.all())

        updated = update_client_full(
            instance=party,
            validated_data={
                "contacts": [
                    {
                        "id": primary.pk,
                        "name": "Contato principal",
                        "position": "",
                        "phone": "1130833391",
                        "mobile": "11999999999",
                        "email": "principal@example.com",
                        "is_primary": True,
                        "is_active": True,
                    },
                    {
                        "name": "Novo contato",
                        "position": "Compras",
                        "phone": "1331543146",
                        "mobile": "13931543146",
                        "email": "novo@example.com",
                        "is_primary": False,
                        "is_active": True,
                    },
                ],
            },
            user=None,
        )

        response_data = ClientFullSerializer(updated).data

        self.assertEqual(Contact.objects.filter(party=party).count(), 2)
        self.assertEqual(len(response_data["contacts"]), 2)
        self.assertEqual(
            {item["email"] for item in response_data["contacts"]},
            {"principal@example.com", "novo@example.com"},
        )

    def test_requires_cpf_for_individual(self):
        payload = self.valid_payload(
            person_type=PersonType.INDIVIDUAL,
            document="",
        )
        serializer = ClientFullSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn("document", serializer.errors)

    def test_accepts_valid_cpf(self):
        payload = self.valid_payload(
            person_type=PersonType.INDIVIDUAL,
            legal_name="Pessoa Física Teste",
            document="529.982.247-25",
        )
        serializer = ClientFullSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["document"], "52998224725")

    def test_rejects_invalid_cpf(self):
        payload = self.valid_payload(
            person_type=PersonType.INDIVIDUAL,
            document="111.111.111-11",
        )
        serializer = ClientFullSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn("document", serializer.errors)

    def test_rejects_invalid_cnpj(self):
        payload = self.valid_payload(document="11.111.111/1111-11")
        serializer = ClientFullSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn("document", serializer.errors)
