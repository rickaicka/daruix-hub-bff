from django.test import SimpleTestCase
from commercial.serializers import ProposalCommercialDetailsSerializer


class ProposalCommercialDetailsTests(SimpleTestCase):
    def test_accepts_commercial_sections(self):
        s = ProposalCommercialDetailsSerializer(data={
            'billing': {'legal_name': 'Cliente', 'document': '123'},
            'delivery': {'address': 'Rua Teste, 10', 'contact': 'Portaria'},
            'work_tax': {'cno': '12.345'},
            'instructions': {'other': 'Agendar entrega'},
        })
        self.assertTrue(s.is_valid(), s.errors)

    def test_rejects_invalid_email_and_unknown_fields(self):
        s = ProposalCommercialDetailsSerializer(data={'collection': {'email': 'invalido'}})
        self.assertFalse(s.is_valid())
        self.assertIn('collection', s.errors)

    def test_no_fields_is_allowed_for_legacy_proposal(self):
        s = ProposalCommercialDetailsSerializer(data={})
        self.assertTrue(s.is_valid(), s.errors)
