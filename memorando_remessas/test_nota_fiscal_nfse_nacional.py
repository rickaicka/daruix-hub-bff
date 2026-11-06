from django.test import SimpleTestCase
from memorando_remessas.services.nota_fiscal_reader import _parse_ocr_text


class NotaFiscalServicoOCRTest(SimpleTestCase):
    def test_nfse_issuer_cpf_and_liquid_value(self):
        text = '''DANFSe v1.0 Documento Auxiliar da NFS-e
Número da NFS-e
11
EMITENTE DA NFS-e CNPJ / CPF / NIF
Prestador do Serviço 424.840.990-00
Nome / Nome Empresarial
JEAN VITOR DA SILVA LUIZ
TOMADOR DO SERVIÇO CNPJ / CPF
17.339.686/0001-42
DRS INCORPORADORA SPE 03 LTDA
VALOR TOTAL DA NFS-e
Valor Líquido da NFS-e
R$ 600,00'''
        result = _parse_ocr_text(text)
        self.assertEqual(result['number'], '11')
        self.assertEqual(result['issuer_name'], 'JEAN VITOR DA SILVA LUIZ')
        self.assertEqual(result['issuer_document'], '42484099000')
        self.assertEqual(result['total_value'], '600.00')
        self.assertEqual(result['series'], '')

    def test_does_not_confuse_client_cnpj_with_issuer_document(self):
        result = _parse_ocr_text('''DANFSe v1.0 NFS-e
EMITENTE DA NFS-e
JEAN VITOR DA SILVA LUIZ
TOMADOR DO SERVIÇO
CNPJ 17.339.686/0001-42''')
        self.assertNotEqual(result['issuer_document'], '17339686000142')
