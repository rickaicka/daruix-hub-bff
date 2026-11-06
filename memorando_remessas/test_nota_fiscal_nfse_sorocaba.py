from django.test import SimpleTestCase
from memorando_remessas.services.nota_fiscal_reader import _parse_ocr_text

class SorocabaNfseOCRTest(SimpleTestCase):
    def test_recovers_number_issuer_and_net_value_from_scanned_pdf(self):
        text = '''PREFEITURA DE SOROCABA
Nota Fiscal de Serviços Eletrônica - NFS-e
DADOS DA NFS-e
Data e Hora da Emissão Competência da NFS-e Numero / Sério
13/07/2026 17:07:38 07/2026 3737 / U
EMITENTE DA NFS-o
CPF/CNPJ: Inscrição Municipal:
01,415.150/0001-29
Nome/Razão Social
PREMODISA SOROCABA SISTEMAS PRE-MOLDADOS LTDA E-mail
financeiro@premodisa.com.br
TOMADOR DO SERVIÇO
CPF/CNPJ
10.250.585/0012-04
VALOR TOTAL DA NOTA
Base Cálculo ISSQN (R$) Retenções (R$) Descontos (R$) Valor Liquido (R$)
1.665.000,00 138.195,00 0,00 1.526.805,00
INFORMAÇÕES COMPLEMENTARES'''
        r = _parse_ocr_text(text)
        self.assertEqual((r['number'], r['series']), ('3737', 'U'))
        self.assertEqual(r['issuer_name'], 'PREMODISA SOROCABA SISTEMAS PRE-MOLDADOS LTDA')
        self.assertEqual(r['issuer_document'], '01415150000129')
        self.assertEqual(r['total_value'], '1526805.00')

    def test_photo_must_not_use_unreliable_bank_transfer_amount(self):
        text = '''Nota Fiscal de Serviços Eletrônica - NFS-e
DADOS DA NFS-e
Numero / Série
13/07/2026 17:07:38 07/2026 3737 /U
EMITENTE DA NFS-e
CPF/CNPJ
01,415.150/0001-29
Nome/Razão Social
PREMODISA SOROCABA SISTEMAS PRE-MOLDADOS LTDA E-mail
financeirofbpremodisa com br
TOMADOR DO SERVICO
10.250.585/0012-04
VALOR LÍQUIDO R$ 4 524 805,00
VALOR TOTAL DA NOTA
Base Cálculo ISSQN (R$) Retenções (R$) Descontos (R$) Valor Liquido (R$)
1665 000 00 ata dan am eee'''
        r = _parse_ocr_text(text)
        self.assertEqual(r['number'], '3737')
        self.assertEqual(r['issuer_name'], 'PREMODISA SOROCABA SISTEMAS PRE-MOLDADOS LTDA')
        self.assertIsNone(r['total_value'])

    def test_national_nfse_remains_supported(self):
        text = '''DANFSe v1.0 Documento Auxiliar da NFS-e
Número da NFS-e
11
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
        self.assertEqual(r['total_value'], '600.00')
