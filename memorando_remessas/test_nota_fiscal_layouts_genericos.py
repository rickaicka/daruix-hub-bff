from django.test import SimpleTestCase
from memorando_remessas.services.nota_fiscal_reader import _parse_ocr_text


class LayoutsGenericosTest(SimpleTestCase):
    def test_nfse_municipal_prestador_numero_e_valor(self):
        text = '''PREFEITURA MUNICIPAL
NOTA FISCAL DE SERVIÇO ELETRÔNICA - NFS-e
NFS-e
673
Código de Verificação
Prestador de Serviço
CPF/CNPJ 09.650.452/0001-93
Nome/Razão Social E.F.C LOCACOES DE MAQUINAS LTDA
Tomador de Serviço
CPF/CNPJ 10.250.585/0012-04
Detalhamento de Valores (R$)
Valor do Serviço 88.865,03
Valor Líquido 88.865,03'''
        r = _parse_ocr_text(text)
        self.assertEqual(r['number'], '673')
        self.assertEqual(r['issuer_name'], 'E.F.C LOCACOES DE MAQUINAS LTDA')
        self.assertEqual(r['issuer_document'], '09650452000193')
        self.assertEqual(r['total_value'], '88865.03')

    def test_numero_curto_nacional_com_rotulo(self):
        text = '''DANFSe v1.0 Documento Auxiliar da NFS-e
Número da NFS-e
11
Competência da NFS-e
20/10/2026
EMITENTE DA NFS-e
Prestador do Serviço 424.840.990-00
Nome / Nome Empresarial
JEAN VITOR DA SILVA LUIZ
TOMADOR DO SERVIÇO
17.339.686/0001-42
VALOR TOTAL DA NFS-e
Valor Líquido da NFS-e
R$ 600,00'''
        r = _parse_ocr_text(text)
        self.assertEqual(r['number'], '11')
        self.assertEqual(r['issuer_document'], '42484099000')
        self.assertEqual(r['total_value'], '600.00')

    def test_nao_extrai_cnpj_do_tomador(self):
        text = '''NOTA FISCAL DE SERVIÇO ELETRÔNICA - NFS-e
Prestador de Serviço
Nome/Razão Social EMPRESA TESTE LTDA
Tomador de Serviço
CPF/CNPJ 10.250.585/0012-04'''
        r = _parse_ocr_text(text)
        self.assertNotEqual(r['issuer_document'], '10250585001204')
