from django.test import SimpleTestCase
from memorando_remessas.services.nota_fiscal_reader import _parse_ocr_text


class GenericDamagedNfseOCRTest(SimpleTestCase):
    def test_damaged_issuer_heading_does_not_prevent_issuer_or_amount(self):
        text = '''DANFSe v1.0 Documento Auxiliar da NFS-e
Número Competência de NFG-
Prestador do Serviço 43.834 493/0001-78 (11) 4172-2067
Nome / Nome Empresarial Email
CLEITON ALVES DA SILVA 23058620893 JESSICASANTOSFERRAZ@HOTMAIL COM
TOMADOR DO SERVICO
47,479.727/0001-67
Nome / Nome Empresarial
DARUIX JARDIM DAS FLORES SPE 01 LTDA
VALORTOTALDANFSE
Valor Liquido da NFS-e
R$ 5.427,00
'''
        result = _parse_ocr_text(text)
        self.assertEqual(result['issuer_name'], 'CLEITON ALVES DA SILVA 23058620893')
        self.assertEqual(result['issuer_document'], '43834493000178')
        self.assertEqual(result['total_value'], '5427.00')
        self.assertFalse(result['number'])  # OCR não trouxe número confiável

    def test_no_recipient_document_mistaken_for_issuer(self):
        text = '''DANFSe v1.0
Prestador do Serviço
Nome / Nome Empresarial
EMPRESA EXEMPLO LTDA
TOMADOR DO SERVICO
47.479.727/0001-67
Valor Liquido da NFS-e
R$ 100,00'''
        result = _parse_ocr_text(text)
        self.assertNotEqual(result['issuer_document'], '47479727000167')
