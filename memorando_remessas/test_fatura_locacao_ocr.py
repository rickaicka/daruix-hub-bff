from django.test import SimpleTestCase
from memorando_remessas.services.nota_fiscal_reader import _parse_fatura_locacao


class FaturaLocacaoOCRTest(SimpleTestCase):
    def test_fatura_sem_cnpj_do_locador_nao_usa_cnpj_do_destinatario(self):
        text = '''CPL Locação de Máquinas e Equipamentos Ltd
FATURA DE LOCAÇÃO DE BENS MÓVEIS
DESTINATARIO
CNPJ 10.250.585/0012-04
FATURA
Nº 132534 VALOR 650,00
VALOR TOTAL R$ 650,00
'''
        result = _parse_fatura_locacao(text)
        self.assertEqual(result['number'], '132534')
        self.assertEqual(result['total_value'], '650.00')
        self.assertEqual(result['issuer_document'], '')
        self.assertIn('Fatura de locação', result['warnings'][0])

    def test_ocr_sem_legenda_numero_e_nome_do_locador(self):
        text = '''£ CPL Locação de Máquinas e Equipamentos Ltd
FATURA DE LOCAÇÃO DE BENS MÓVEIS
DESTINATARIO
FATURA
we 132534 VALOR: 650,00
VALOR TOTAL R$
650,00'''
        result = _parse_fatura_locacao(text)
        self.assertEqual(result['number'], '132534')
        self.assertTrue(result['issuer_name'].lower().startswith('cpl locação'))
        self.assertEqual(result['total_value'], '650.00')

    def test_nao_classifica_nfse_como_fatura(self):
        self.assertIsNone(_parse_fatura_locacao('NOTA FISCAL DE SERVIÇOS ELETRÔNICA - NFS-e\nVALOR TOTAL 650,00'))
