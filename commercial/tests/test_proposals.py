from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from commercial.models import (
    Address,
    Contact,
    Department,
    Division,
    Party,
    PartyType,
    PersonType,
    Project,
    Proposal,
    ProposalContact,
    ProposalInstallment,
    ProposalRequestedService,
    ProposalStatus,
    ProposalType,
)
from commercial.services.proposals import accept_proposal


class ProposalDomainTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ricardo", email="ricardo@example.com", name="Ricardo", password="test")
        self.party = Party.objects.create(person_type=PersonType.COMPANY, legal_name="Interessado Teste")
        self.address = Address.objects.create(party=self.party, postal_code="01001-000", street="Praça da Sé", number="1", district="Sé", city="São Paulo", state="SP")
        self.contact = Contact.objects.create(party=self.party, name="Contato Teste", email="contato@example.com")
        self.division = Division.objects.create(name="DEC", code="DEC", origin="HUB")
        self.department = Department.objects.create(name="Estrutura", division=self.division, origin="HUB")
        self.proposal_type = ProposalType.objects.create(name="Estrutura", origin="HUB")
        self.project = Project.objects.create(name="Projeto estrutural", department=self.department, origin="HUB")

    def make_proposal(self, **changes):
        data = dict(party=self.party, work_address=self.address, requester_contact=self.contact, entry_date=date(2026, 8, 24), division=self.division, department=self.department, work_name="Obra", proposal_type=self.proposal_type, technical_responsible=self.user, issuer=self.user, status=ProposalStatus.SENT)
        data.update(changes)
        return Proposal.objects.create(**data)

    def test_accepting_proposal_promotes_interested_party(self):
        proposal = accept_proposal(proposal=self.make_proposal())
        self.party.refresh_from_db()
        self.assertEqual(proposal.status, ProposalStatus.ACCEPTED)
        self.assertEqual(self.party.party_type, PartyType.CLIENT)
        self.assertIsNotNone(self.party.converted_at)

    def test_proposal_rejects_contact_from_another_party(self):
        other = Party.objects.create(person_type=PersonType.COMPANY, legal_name="Outro")
        other_contact = Contact.objects.create(party=other, name="Contato de outro")
        with self.assertRaises(ValidationError):
            self.make_proposal(requester_contact=other_contact)

    def test_proposal_rejects_department_from_another_division(self):
        other_division = Division.objects.create(name="DAQ", code="DAQ", origin="HUB")
        other_department = Department.objects.create(name="Arquitetura", division=other_division, origin="HUB")

        with self.assertRaises(ValidationError):
            self.make_proposal(department=other_department)

    def test_proposal_supports_relational_tabs(self):
        proposal = self.make_proposal()

        service = ProposalRequestedService.objects.create(
            proposal=proposal,
            project=self.project,
            proposed_value="1500.00",
        )
        proposal_contact = ProposalContact.objects.create(
            proposal=proposal,
            contact=self.contact,
        )
        installment = ProposalInstallment.objects.create(
            proposal=proposal,
            label="Única",
            sequence=1,
            amount="1500.00",
        )

        self.assertEqual(service.proposal_id, proposal.id)
        self.assertEqual(proposal_contact.contact_id, self.contact.id)
        self.assertEqual(installment.proposal_id, proposal.id)

    def test_legacy_proposal_allows_optional_children_and_users(self):
        proposal = Proposal.objects.create(
            origin="LEGACY",
            legacy_id=7510,
            code="PC21065",
            party=self.party,
            entry_date=date(2021, 5, 21),
            division=self.division,
            department=self.department,
            work_name="BEM BARATO MAUÁ LOJA 19",
            status=ProposalStatus.ACCEPTED,
        )

        self.assertIsNone(proposal.work_address)
        self.assertIsNone(proposal.requester_contact)
        self.assertIsNone(proposal.issuer)
