"""Testes de regressão para DANFE digitalizado, sem depender de OCR na CI."""
from django.test import SimpleTestCase
from memorando_remessas.services.nota_fiscal_reader import _parse_ocr_text


class DanfeScannedOCRTest(SimpleTestCase):
    SAMPLE = '''
NF-e
Nº 000.050.264
SÉRIE 001
PONCE COMERCIO DE TINTAS LTDA DOCUMENTO AUXILIAR
CHAVE DE ACESSO
59.455.451/0001-66
DESTINATÁRIO / REMETENTE
DRS INCORPORADORA SPE 03 LTDA
CÁLCULO DO IMPOSTO
VALOR TOTAL DOS PRODUTOS
764,10
DESCONTO OUTRAS DESPESAS VALOR TOTALDA NOTA
0,00 0,00 76,40 0,00 687,70
'''

    def test_scanned_danfe_header_and_total(self):
        result = _parse_ocr_text(self.SAMPLE)
        self.assertEqual(result['number'], '000050264')
        self.assertEqual(result['series'], '001')
        self.assertEqual(result['issuer_name'], 'PONCE COMERCIO DE TINTAS LTDA')
        self.assertEqual(result['issuer_document'], '59455451000166')
        self.assertEqual(result['total_value'], '687.70')

    def test_does_not_take_recipient_cnpj_as_issuer(self):
        result = _parse_ocr_text('NF-e\nNº 000.050.264\nDESTINATÁRIO / REMETENTE\n17.339.686/0001-42')
        self.assertFalse(result['issuer_document'])
