from django.test import TestCase
from django.utils import timezone

from commercial.models import (
    InstallmentSource,
    PartyType,
    Proposal,
    ProposalInstallment,
    ProposalRequestedService,
)
from commercial.services.legacy_proposals import (
    LegacyProposalImporter,
    optional_decimal,
    optional_datetime,
    repair_legacy_text,
)


class LegacyProposalImporterTests(TestCase):
    def payload(self):
        return {
            "proposal_types": [
                {
                    "tipoPropostaID": 15,
                    "tipoDePropostaNome": "Arquitetura",
                }
            ],
            "departments": [
                {
                    "departamentoID": 5,
                    "Departamento": "Obra",
                    "divisao": "DEC",
                    "departamentoSigla": "O",
                }
            ],
            "projects": [
                {
                    "projetoID": 7,
                    "Projeto": "Arquitetura",
                    "Departamento": "Obra",
                }
            ],
            "proposals": [
                {
                    "propostaID": 7510,
                    "PC": "PC21065",
                    "Cliente": "FAIAS PAIVA ADMINISTRAÃÃO E PARTICIPAÃÃES S.A.",
                    "clienteID": None,
                    "DataDeEntrada": "2021-05-21T00:00",
                    "Obra": "BEM BARATO MAUÃ LOJA 19",
                    "DescriÃ§Ã£o": "EXECUÃÃO",
                    "DivisÃ£o": "DEC",
                    "Posicao": "Aprovado",
                    "propDepartamento": "Obras",
                    "tipoProposta": "Arquitetura",
                    "Contato1P": "Marco",
                    "Celular1P": "11999999999",
                    "valorDoContrato": "12000.0000",
                    "valorAdicional": "500.0000",
                }
            ],
            "requested_services": [
                {
                    "projetoPropostaID": 302,
                    "PC": "PC21065",
                    "propostaID": None,
                    "Projeto": "Arquitetura",
                    "projetoID": 7,
                    "valor_projeto": "12000.0000",
                }
            ],
            "proposal_contacts": [],
            "payment_installments": [
                {
                    "pppId": 2,
                    "pppPC": "PC21065",
                    "pppParcela": "Ãnica",
                    "pppValor": "12500.0000",
                    "pppVencimento": "2021-06-21T00:00",
                    "pppSituacao": "Quitada",
                }
            ],
            "payment_plans": [
                {
                    "codigo_planpag": 55,
                    "PC": "PC21065",
                    "valor_parcela": "999.0000",
                    "Parcela": "1Âª",
                    "status": "Em Aberto",
                }
            ],
        }

    def test_repairs_legacy_text(self):
        self.assertEqual(repair_legacy_text("AdministraÃ§Ã£o"), "Administração")

    def test_normalizes_legacy_money_to_two_decimal_places(self):
        self.assertEqual(str(optional_decimal("12000.0000")), "12000.00")
        self.assertEqual(str(optional_decimal("10.235")), "10.24")

    def test_converts_legacy_datetime_to_current_timezone(self):
        parsed = optional_datetime("2003-07-01T00:00:00")

        self.assertTrue(timezone.is_aware(parsed))

    def test_imports_relations_and_prefers_installment_table(self):
        payload = self.payload()
        LegacyProposalImporter().import_all(**payload)

        proposal = Proposal.objects.select_related(
            "party",
            "division",
            "department",
            "proposal_type",
            "requester_contact",
        ).get(code="PC21065")

        self.assertEqual(proposal.legacy_id, 7510)
        self.assertEqual(proposal.party.party_type, PartyType.CLIENT)
        self.assertEqual(proposal.division.code, "DEC")
        self.assertEqual(proposal.department.name, "Obra")
        self.assertEqual(proposal.proposal_type.name, "Arquitetura")
        self.assertEqual(proposal.requester_contact.name, "Marco")
        self.assertIn("MAUÁ", proposal.work_name)
        self.assertEqual(ProposalRequestedService.objects.count(), 1)

        installment = ProposalInstallment.objects.get(proposal=proposal)
        self.assertEqual(installment.source, InstallmentSource.LEGACY_INSTALLMENTS)
        self.assertEqual(installment.amount, 12500)

    def test_import_is_idempotent(self):
        payload = self.payload()
        LegacyProposalImporter().import_all(**payload)
        LegacyProposalImporter().import_all(**payload)

        self.assertEqual(Proposal.objects.filter(code="PC21065").count(), 1)
        self.assertEqual(ProposalRequestedService.objects.count(), 1)
        self.assertEqual(ProposalInstallment.objects.count(), 1)
