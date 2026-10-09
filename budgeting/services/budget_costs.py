from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from budgeting.choices import BudgetSheetItemType, SupplyType
from budgeting.models import BudgetSheet, BudgetSheetStageItem
from budgeting.services.budget_sheets import ensure_budget_sheet_editable

PERCENT_4 = Decimal("0.0001")
QUANTITY_6 = Decimal("0.000001")
COST_4 = Decimal("0.0001")
FACTOR_12 = Decimal("0.000000000001")
MONEY_2 = Decimal("0.01")
ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")

# Guia B.D.I. da PC25104. Os percentuais abaixo compõem o bloco (D)
# "Lucro/Administração e outros". Encargos financeiros aparece na memória
# detalhada do Excel, mas NÃO entra no SUM de D16.
BDI_NON_TAX_KEYS = (
    "lucro",
    "imprevistos",
    "comercial",
    "seguros",
    "reserva_tecnica",
    "administracao_central",
)
BDI_TAX_KEYS = (
    "ir_imposto_renda_lucro",
    "cs_contribuicao_social_lucro",
    "iss",
    "pis",
    "cofins",
    "diferencas_impostos",
    "imposto_sobre_lucro",
)

BDI_TEMPLATE: dict[str, Any] = {
    "version": 3,
    "kind": "BDI",
    "title": "B.D.I.",
    "description": (
        "Memória de cálculo do BDI desta revisão baseada na guia B.D.I. "
        "da planilha orçamentária. Existe um único valor percentual por linha."
    ),
    "columns": [
        {"key": "discrimination", "label": "Discriminação", "editable": False, "type": "text"},
        {"key": "unit", "label": "Un.", "editable": False, "type": "text"},
        {"key": "percentage", "label": "%", "editable": True, "type": "percentage"},
        {"key": "amount", "label": "Valor (R$)", "editable": False, "type": "currency"},
    ],
    "rows": [
        {"key": "lucro", "discrimination": "LUCRO", "unit": "%", "values": {}},
        {"key": "ir_imposto_renda_lucro", "discrimination": "IR - Imposto de Renda sobre lucro", "unit": "%", "values": {}},
        {"key": "cs_contribuicao_social_lucro", "discrimination": "CS - Contribuição Social sobre lucro", "unit": "%", "values": {}},
        {"key": "iss", "discrimination": "ISS", "unit": "%", "values": {}},
        {"key": "pis", "discrimination": "PIS", "unit": "%", "values": {}},
        {"key": "cofins", "discrimination": "COFINS", "unit": "%", "values": {}},
        {"key": "diferencas_impostos", "discrimination": "DIFERENÇAS DE IMPOSTOS", "unit": "%", "values": {}},
        {"key": "imposto_sobre_lucro", "discrimination": "IMPOSTO SOBRE LUCRO", "unit": "%", "values": {}},
        {"key": "imprevistos", "discrimination": "IMPREVISTOS", "unit": "%", "values": {}},
        {"key": "comercial", "discrimination": "COMERCIAL", "unit": "%", "values": {}},
        {"key": "seguros", "discrimination": "SEGUROS", "unit": "%", "values": {}},
        {"key": "reserva_tecnica", "discrimination": "RESERVA TÉCNICA", "unit": "%", "values": {}},
        {"key": "encargos_financeiros", "discrimination": "ENCARGOS FINANCEIROS", "unit": "%", "values": {}},
        {"key": "administracao_central", "discrimination": "ADMINISTRAÇÃO CENTRAL (escritório)", "unit": "%", "values": {}},
    ],
}

# Linhas estruturais da tabela principal da guia D.I. da PC25104.
# Os valores numéricos do arquivo de exemplo NÃO são copiados como defaults:
# cada revisão começa zerada e recebe seus próprios quantitativos/custos.
DI_TEMPLATE_ROWS: list[dict[str, Any]] = [{'key': 'group_01', 'item': '01', 'discrimination': 'CONSUMOS', 'unit': '', 'row_type': 'GROUP', 'group': '01'},
 {'key': '01_01',
  'item': '01.01',
  'discrimination': 'Consumo de materiais de escritório',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '01'},
 {'key': '01_02',
  'item': '01.02',
  'discrimination': 'Consumo de medicamentos de emergência',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '01'},
 {'key': '01_03',
  'item': '01.03',
  'discrimination': 'Aluguel de computador / impressora',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '01'},
 {'key': '01_04',
  'item': '01.04',
  'discrimination': 'Aluguel de telefone',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '01'},
 {'key': '01_05',
  'item': '01.05',
  'discrimination': 'Consumo de telefone',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '01'},
 {'key': '01_06',
  'item': '01.06',
  'discrimination': 'Consumo de água',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '01'},
 {'key': '01_07',
  'item': '01.07',
  'discrimination': 'Consumo de energia',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '01'},
 {'key': '01_08',
  'item': '01.08',
  'discrimination': 'Alimentação pessoal administrativo',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '01'},
 {'key': '01_09',
  'item': '01.09',
  'discrimination': 'Alimentação pessoal direto (operário)',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '01'},
 {'key': '01_10',
  'item': '01.10',
  'discrimination': 'Transporte pessoal administrativo',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '01'},
 {'key': '01_11',
  'item': '01.11',
  'discrimination': 'Transporte pessoal direto (operário)',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '01'},
 {'key': '01_12',
  'item': '01.12',
  'discrimination': 'Equipamento de Proteção Individual (EPI)',
  'unit': 'vb',
  'row_type': 'ITEM',
  'group': '01'},
 {'key': '01_13', 'item': '01.13', 'discrimination': 'Horas Extras', 'unit': 'vb', 'row_type': 'ITEM', 'group': '01'},
 {'key': '01_14',
  'item': '01.14',
  'discrimination': 'Plotagens / cópias xérox / cópias heliográficas',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '01'},
 {'key': '01_15',
  'item': '01.15',
  'discrimination': 'Controle tecnológico do concreto e aço',
  'unit': 'vb',
  'row_type': 'ITEM',
  'group': '01'},
 {'key': '01_16',
  'item': '01.16',
  'discrimination': 'Controle tecnológico do solo',
  'unit': 'vb',
  'row_type': 'ITEM',
  'group': '01'},
 {'key': '01_17',
  'item': '01.17',
  'discrimination': 'Passagem de avião',
  'unit': 'vb',
  'row_type': 'ITEM',
  'group': '01'},
 {'key': '01_18',
  'item': '01.18',
  'discrimination': 'Estadia / Hotel',
  'unit': 'dia',
  'row_type': 'ITEM',
  'group': '01'},
 {'key': '01_19',
  'item': '01.19',
  'discrimination': 'Gasolina /Álcool / Diesel',
  'unit': 'km',
  'row_type': 'ITEM',
  'group': '01'},
 {'key': '01_20',
  'item': '01.20',
  'discrimination': 'Aluguel de casa para pessoal da obra',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '01'},
 {'key': '01_21',
  'item': '01.21',
  'discrimination': 'Fretes e carretos',
  'unit': 'vb',
  'row_type': 'ITEM',
  'group': '01'},
 {'key': 'group_02', 'item': '02', 'discrimination': 'EQUIPAMENTOS', 'unit': '', 'row_type': 'GROUP', 'group': '02'},
 {'key': '02_01',
  'item': '02.01',
  'discrimination': 'Betoneira 320 litros motor trifásico, pot. 3HP 220V',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '02'},
 {'key': '02_02',
  'item': '02.02',
  'discrimination': 'Serra circular 7"',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '02'},
 {'key': '02_03',
  'item': '02.03',
  'discrimination': 'Máquina de cortar ferro',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '02'},
 {'key': '02_04', 'item': '02.04', 'discrimination': 'Serra manual', 'unit': 'mês', 'row_type': 'ITEM', 'group': '02'},
 {'key': '02_05',
  'item': '02.05',
  'discrimination': 'Compactador de solos tipo sapo elétrico 220V',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '02'},
 {'key': '02_06',
  'item': '02.06',
  'discrimination': 'Diversos manuais',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '02'},
 {'key': '02_07',
  'item': '02.07',
  'discrimination': 'Andaime metálico tubular 1,00 x 2,00m',
  'unit': 'm²/mês',
  'row_type': 'ITEM',
  'group': '02'},
 {'key': '02_08',
  'item': '02.08',
  'discrimination': 'Andaime fachadeiro 1,00 x 2,00 x 1,00m',
  'unit': 'm²/mês',
  'row_type': 'ITEM',
  'group': '02'},
 {'key': '02_09', 'item': '02.09', 'discrimination': 'Guincho veloz', 'unit': 'mês', 'row_type': 'ITEM', 'group': '02'},
 {'key': '02_10',
  'item': '02.10',
  'discrimination': 'Martelete elétrico, com potência de 2KW e diâmetro do furo de 28mm',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '02'},
 {'key': '02_11',
  'item': '02.11',
  'discrimination': 'Furadeira manual, modelo 1/2", com rotação de 1.300 por minuto',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '02'},
 {'key': '02_12',
  'item': '02.12',
  'discrimination': 'Torre monta carga',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '02'},
 {'key': '02_13',
  'item': '02.13',
  'discrimination': 'Vibrador concreto, elétrico, com potência de 5 HP',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '02'},
 {'key': '02_14',
  'item': '02.14',
  'discrimination': 'LOCAÇÃO DE FERRAMENTAS',
  'unit': 'VB',
  'row_type': 'ITEM',
  'group': '02'},
 {'key': 'group_03',
  'item': '03',
  'discrimination': 'CANTEIRO / SERVIÇOS PRELIMINARES',
  'unit': '',
  'row_type': 'GROUP',
  'group': '03'},
 {'key': '03_01',
  'item': '03.01',
  'discrimination': 'Barracão para escritório',
  'unit': 'm2',
  'row_type': 'ITEM',
  'group': '03'},
 {'key': '03_02',
  'item': '03.02',
  'discrimination': 'Fechamento para guarda de materiais',
  'unit': 'm2',
  'row_type': 'ITEM',
  'group': '03'},
 {'key': '03_03',
  'item': '03.03',
  'discrimination': 'Barracão para forma e aço',
  'unit': 'm2',
  'row_type': 'ITEM',
  'group': '03'},
 {'key': '03_04',
  'item': '03.04',
  'discrimination': 'Tapume de compensado com pintura',
  'unit': 'm2',
  'row_type': 'ITEM',
  'group': '03'},
 {'key': '03_05',
  'item': '03.05',
  'discrimination': 'Tapume com divisória',
  'unit': 'm2',
  'row_type': 'ITEM',
  'group': '03'},
 {'key': '03_06',
  'item': '03.06',
  'discrimination': 'Locação de container escritório com 1 sanitário',
  'unit': 'un x mês',
  'row_type': 'ITEM',
  'group': '03'},
 {'key': '03_07',
  'item': '03.07',
  'discrimination': 'Locação de container sanitário',
  'unit': 'un x mês',
  'row_type': 'ITEM',
  'group': '03'},
 {'key': '03_08',
  'item': '03.08',
  'discrimination': 'Frete para container escritório e santiário',
  'unit': 'vg',
  'row_type': 'ITEM',
  'group': '03'},
 {'key': '03_09',
  'item': '03.09',
  'discrimination': 'Transporte horizontal / vertical',
  'unit': 'hs',
  'row_type': 'ITEM',
  'group': '03'},
 {'key': '03_10',
  'item': '03.10',
  'discrimination': 'Ligação provisória de água e esgoto',
  'unit': 'vb',
  'row_type': 'ITEM',
  'group': '03'},
 {'key': '03_11',
  'item': '03.11',
  'discrimination': 'Ligação provisória de energia',
  'unit': 'vb',
  'row_type': 'ITEM',
  'group': '03'},
 {'key': '03_12',
  'item': '03.12',
  'discrimination': 'Rede provisória de água e esgoto',
  'unit': 'vb',
  'row_type': 'ITEM',
  'group': '03'},
 {'key': '03_13',
  'item': '03.13',
  'discrimination': 'Rede provisória de energia',
  'unit': 'vb',
  'row_type': 'ITEM',
  'group': '03'},
 {'key': '03_14', 'item': '03.14', 'discrimination': 'Placas de obra', 'unit': 'vb', 'row_type': 'ITEM', 'group': '03'},
 {'key': '03_15',
  'item': '03.15',
  'discrimination': 'Limpeza do terreno',
  'unit': 'm2',
  'row_type': 'ITEM',
  'group': '03'},
 {'key': '03_16',
  'item': '03.16',
  'discrimination': 'Locação da obra',
  'unit': 'm2',
  'row_type': 'ITEM',
  'group': '03'},
 {'key': '03_17',
  'item': '03.17',
  'discrimination': 'Equipe de topografia',
  'unit': 'dia',
  'row_type': 'ITEM',
  'group': '03'},
 {'key': 'group_04',
  'item': '04',
  'discrimination': 'ADMINISTRAÇÃO DA OBRA',
  'unit': '',
  'row_type': 'GROUP',
  'group': '04'},
 {'key': '04_01',
  'item': '04.01',
  'discrimination': 'Engenheiro (1/2 período)',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '04'},
 {'key': '04_02',
  'item': '04.02',
  'discrimination': 'Mestre de obras',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '04'},
 {'key': '04_03', 'item': '04.03', 'discrimination': 'Encarregado', 'unit': 'mês', 'row_type': 'ITEM', 'group': '04'},
 {'key': '04_04', 'item': '04.04', 'discrimination': 'Apontador', 'unit': 'mês', 'row_type': 'ITEM', 'group': '04'},
 {'key': '04_05', 'item': '04.05', 'discrimination': 'Almoxarife', 'unit': 'mês', 'row_type': 'ITEM', 'group': '04'},
 {'key': '04_06',
  'item': '04.06',
  'discrimination': 'Operador de guincho',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '04'},
 {'key': '04_07', 'item': '04.07', 'discrimination': 'Vigia diurno', 'unit': 'mês', 'row_type': 'ITEM', 'group': '04'},
 {'key': '04_07_2',
  'item': '04.07',
  'discrimination': 'Vigia noturno',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '04'},
 {'key': '04_08', 'item': '04.08', 'discrimination': 'Estagiário', 'unit': 'mês', 'row_type': 'ITEM', 'group': '04'},
 {'key': '04_09',
  'item': '04.09',
  'discrimination': 'Tecnico de Segurança',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '04'},
 {'key': 'group_05',
  'item': '05',
  'discrimination': 'LIMPEZA DA OBRA / SERVIÇOS FINAIS',
  'unit': '',
  'row_type': 'GROUP',
  'group': '05'},
 {'key': '05_01',
  'item': '05.01',
  'discrimination': 'Limpeza permanente de obra',
  'unit': 'mês',
  'row_type': 'ITEM',
  'group': '05'},
 {'key': '05_02',
  'item': '05.02',
  'discrimination': 'Remoção de entulho - caçamba',
  'unit': 'un x mês',
  'row_type': 'ITEM',
  'group': '05'},
 {'key': '05_03',
  'item': '05.03',
  'discrimination': 'Limpeza final de obra',
  'unit': 'm2',
  'row_type': 'ITEM',
  'group': '05'},
 {'key': '05_04',
  'item': '05.04',
  'discrimination': 'Desmobilização da obra',
  'unit': 'vb',
  'row_type': 'ITEM',
  'group': '05'},
 {'key': 'group_06', 'item': '06', 'discrimination': 'PROJETOS', 'unit': '', 'row_type': 'GROUP', 'group': '06'},
 {'key': '06_01',
  'item': '06.01',
  'discrimination': 'Levantamento planialtimétrico',
  'unit': 'm2',
  'row_type': 'ITEM',
  'group': '06'},
 {'key': '06_02', 'item': '06.02', 'discrimination': 'Sondagem', 'unit': 'm', 'row_type': 'ITEM', 'group': '06'},
 {'key': '06_03', 'item': '06.03', 'discrimination': 'Fundações', 'unit': 'm2', 'row_type': 'ITEM', 'group': '06'},
 {'key': '06_04', 'item': '06.04', 'discrimination': 'Estrutura', 'unit': 'm2', 'row_type': 'ITEM', 'group': '06'},
 {'key': '06_05', 'item': '06.05', 'discrimination': 'Arquitetura', 'unit': 'm2', 'row_type': 'ITEM', 'group': '06'},
 {'key': '06_06',
  'item': '06.06',
  'discrimination': 'Instalações elétricas / hidráulicas',
  'unit': 'm2',
  'row_type': 'ITEM',
  'group': '06'},
 {'key': '06_07',
  'item': '06.07',
  'discrimination': 'Ar condicionado',
  'unit': 'm2',
  'row_type': 'ITEM',
  'group': '06'},
 {'key': '06_08', 'item': '06.08', 'discrimination': 'As Built', 'unit': 'm2', 'row_type': 'ITEM', 'group': '06'},
 {'key': '06_09',
  'item': '06.09',
  'discrimination': 'Assessoria de Fundações',
  'unit': 'vb',
  'row_type': 'ITEM',
  'group': '06'},
 {'key': 'group_07', 'item': '07', 'discrimination': 'TAXAS', 'unit': '', 'row_type': 'GROUP', 'group': '07'},
 {'key': '07_01', 'item': '07.01', 'discrimination': 'ART', 'unit': 'vb', 'row_type': 'ITEM', 'group': '07'},
 {'key': '07_02', 'item': '07.02', 'discrimination': 'CET', 'unit': 'vb', 'row_type': 'ITEM', 'group': '07'}]

# Memórias auxiliares existentes abaixo da tabela principal da guia D.I.
# As chaves e ligações reproduzem literalmente as fórmulas do XLS de referência.
# Em particular, I142 alimenta F22 (01.09); I154 não é referenciado pela tabela
# principal; I166/I178/I190/I215 alimentam 01.10/01.11/01.12/01.13.
DI_AUXILIARY_TABLES: list[dict[str, Any]] = [
    {
        "key": "01_08", "item": "01.08",
        "title": "Alimentação pessoal direto (operário)",
        "formula": "SUM(lines.total)", "target": {"row": "01_09", "column": "material"},
        "calculation": "LINE_TOTAL",
        "rows": [
            {"key": "01_08_cesta", "discrimination": "Cesta básica", "unit": "un", "unit_price": "40.0000"},
            {"key": "01_08_cafe", "discrimination": "Café da manhã", "unit": "un", "unit_price": "3.5000"},
            {"key": "01_08_almoco", "discrimination": "Almoço", "unit": "un", "unit_price": "12.5000"},
            {"key": "01_08_jantar", "discrimination": "Jantar", "unit": "un", "unit_price": "12.5000"},
        ],
    },
    {
        "key": "01_09", "item": "01.09",
        "title": "Transporte pessoal indireto (operário)",
        "formula": "SUM(lines.total)", "target": None, "calculation": "TRANSPORT",
        "rows": [
            {"key": "01_09_onibus_urbano", "discrimination": "Passagem de ônibus urbano", "unit": "un", "unit_price": "3.0000", "role": "FARE"},
            {"key": "01_09_onibus_intermunicipal", "discrimination": "Passagem de ônibus intermunicipal", "unit": "un", "unit_price": "3.0000", "role": "FARE"},
            {"key": "01_09_metro", "discrimination": "Passagem de metrô", "unit": "un", "unit_price": "2.6500", "role": "FARE"},
            {"key": "01_09_trem", "discrimination": "Passagem de trem", "unit": "un", "unit_price": "2.6500", "role": "FARE"},
            {"key": "01_09_pessoas", "discrimination": "Quantidade de pessoas", "unit": "un", "role": "PEOPLE"},
            {"key": "01_09_passagens", "discrimination": "Quantidade de passagem por pessoa", "unit": "un", "role": "RIDES"},
            {"key": "01_09_periodo", "discrimination": "Período de utilização mensal", "unit": "un", "role": "PERIOD"},
        ],
    },
    {
        "key": "01_10", "item": "01.10", "title": "Transporte pessoal administrativo",
        "formula": "SUM(lines.total)", "target": {"row": "01_10", "column": "material"}, "calculation": "TRANSPORT",
        "rows": [
            {"key": "01_10_onibus_urbano", "discrimination": "Passagem de ônibus urbano", "unit": "un", "unit_price": "3.0000", "role": "FARE"},
            {"key": "01_10_onibus_intermunicipal", "discrimination": "Passagem de ônibus intermunicipal", "unit": "un", "unit_price": "3.0000", "role": "FARE"},
            {"key": "01_10_metro", "discrimination": "Passagem de metrô", "unit": "un", "unit_price": "2.6500", "role": "FARE"},
            {"key": "01_10_trem", "discrimination": "Passagem de trem", "unit": "un", "unit_price": "2.6500", "role": "FARE"},
            {"key": "01_10_pessoas", "discrimination": "Quantidade de pessoas", "unit": "un", "role": "PEOPLE"},
            {"key": "01_10_passagens", "discrimination": "Quantidade de passagem por pessoa", "unit": "un", "role": "RIDES"},
            {"key": "01_10_periodo", "discrimination": "Período de utilização mensal", "unit": "un", "role": "PERIOD"},
        ],
    },
    {
        "key": "01_11", "item": "01.11", "title": "Transporte pessoal direto (operário)",
        "formula": "SUM(lines.total)", "target": {"row": "01_11", "column": "material"}, "calculation": "TRANSPORT",
        "rows": [
            {"key": "01_11_onibus_urbano", "discrimination": "Passagem de ônibus urbano", "unit": "un", "unit_price": "3.0000", "role": "FARE"},
            {"key": "01_11_onibus_intermunicipal", "discrimination": "Passagem de ônibus intermunicipal", "unit": "un", "unit_price": "3.0000", "role": "FARE"},
            {"key": "01_11_metro", "discrimination": "Passagem de metrô", "unit": "un", "unit_price": "2.6500", "role": "FARE"},
            {"key": "01_11_trem", "discrimination": "Passagem de trem", "unit": "un", "unit_price": "2.6500", "role": "FARE"},
            {"key": "01_11_pessoas", "discrimination": "Quantidade de pessoas", "unit": "un", "role": "PEOPLE"},
            {"key": "01_11_passagens", "discrimination": "Quantidade de passagem por pessoa", "unit": "un", "role": "RIDES"},
            {"key": "01_11_periodo", "discrimination": "Período de utilização mensal", "unit": "un", "role": "PERIOD"},
        ],
    },
    {
        "key": "01_12", "item": "01.12", "title": "Equipamento de Proteção Individual (EPI)",
        "formula": "SUM(lines.total)", "target": {"row": "01_12", "column": "material"}, "calculation": "LINE_TOTAL",
        "rows": [
            {"key": "01_12_capacete_amarelo", "discrimination": "Capacete amarelo", "unit": "un", "unit_price": "6.5000"},
            {"key": "01_12_capacete_branco", "discrimination": "Capacete branco com jug e catacra", "unit": "un", "unit_price": "40.0000"},
            {"key": "01_12_oculos", "discrimination": "Óculos de proteção", "unit": "un", "unit_price": "2.8000"},
            {"key": "01_12_protetor", "discrimination": "Protetor auricular", "unit": "par", "unit_price": "1.0000"},
            {"key": "01_12_bota", "discrimination": "Bota de borracha cano médio", "unit": "par", "unit_price": "20.0000"},
            {"key": "01_12_luva_raspa", "discrimination": "Luva de raspa", "unit": "par", "unit_price": "8.0000"},
            {"key": "01_12_luva_pvc", "discrimination": "Luva de pvc", "unit": "par", "unit_price": "3.5000"},
            {"key": "01_12_luva_vaqueta", "discrimination": "Luva de vaqueta", "unit": "par", "unit_price": "11.5000"},
            {"key": "01_12_luva_malha", "discrimination": "Luva de malha pigmentada", "unit": "par", "unit_price": "1.2000"},
            {"key": "01_12_mascara", "discrimination": "Máscara descartável", "unit": "un", "unit_price": "0.8500"},
            {"key": "01_12_cinto", "discrimination": "Cinto de segurança tipo paraquedista", "unit": "un", "unit_price": "55.0000"},
        ],
    },
    {
        "key": "01_13", "item": "01.13", "title": "Horas Extras",
        "formula": "SUM(lines.total)", "target": {"row": "01_13", "column": "labor"}, "calculation": "OVERTIME",
        "rows": [
            {"key": "01_13_servente_60", "discrimination": "Servente 60%", "unit": "hh", "factor": "1.6000", "unit_price": "8.5600"},
            {"key": "01_13_oficial_60", "discrimination": "Oficial 60%", "unit": "hh", "factor": "1.6000", "unit_price": "10.2200"},
            {"key": "01_13_servente_100", "discrimination": "Servente 100%", "unit": "hh", "factor": "2.0000", "unit_price": "8.5600"},
            {"key": "01_13_oficial_100", "discrimination": "Oficial 100%", "unit": "hh", "factor": "2.0000", "unit_price": "10.2200"},
        ],
    },
]

DI_TEMPLATE: dict[str, Any] = {
    "version": 4,
    "kind": "DI",
    "title": "D.I.",
    "description": (
        "Despesas indiretas desta revisão. Item, Discriminação e Unidade são "
        "estruturais. Quantidade, Material e Mão de obra são editáveis. "
        "Unitário e Custo total são calculados. Inclui as memórias auxiliares "
        "01.08 a 01.13 da guia D.I."
    ),
    "columns": [
        {"key": "item", "label": "Item", "editable": False, "type": "text"},
        {"key": "discrimination", "label": "Discriminação", "editable": False, "type": "text"},
        {"key": "unit", "label": "Un.", "editable": False, "type": "text"},
        {"key": "quantity", "label": "Quant.", "editable": True, "type": "number"},
        {"key": "material", "label": "Material", "editable": True, "type": "currency"},
        {"key": "labor", "label": "Mão de obra", "editable": True, "type": "currency"},
        {"key": "unit_price", "label": "Unitário", "editable": False, "type": "currency"},
        {"key": "total", "label": "Custo total (R$)", "editable": False, "type": "currency"},
    ],
    "rows": DI_TEMPLATE_ROWS,
    "auxiliary_tables": DI_AUXILIARY_TABLES,
}

BDI_LEGACY_KEY_ALIASES = {
    "seguro_garantia": "seguros",
    "risco": "imprevistos",
    "despesas_financeiras": "encargos_financeiros",
    "tributos": "diferencas_impostos",
}


def _raise_field_error(field: str, message: str) -> None:
    raise ValidationError({field: message})


def _decimal(value: Any, *, field: str) -> Decimal:
    if isinstance(value, str):
        normalized = value.strip()
        if "," in normalized:
            normalized = normalized.replace(".", "").replace(",", ".")
    else:
        normalized = str(value if value is not None else "0").strip()

    try:
        result = Decimal(normalized or "0")
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValidationError({field: "Informe um valor numérico válido."}) from error

    if result < 0:
        raise ValidationError({field: "O valor não pode ser negativo."})
    return result


def _format(value: Decimal, quantum: Decimal) -> str:
    return format(value.quantize(quantum, rounding=ROUND_HALF_UP), "f")


def _format4(value: Decimal) -> str:
    return _format(value, COST_4)


def _format6(value: Decimal) -> str:
    return _format(value, QUANTITY_6)


def _money2(value: Decimal) -> Decimal:
    return Decimal(value or 0).quantize(MONEY_2, rounding=ROUND_HALF_UP)


def _money_string(value: Decimal) -> str:
    return format(_money2(value), "f")


def _breakdown(material: Decimal = ZERO, labor: Decimal = ZERO, total: Decimal | None = None) -> dict[str, str]:
    material = _money2(material)
    labor = _money2(labor)
    normalized_total = _money2(total if total is not None else material + labor)
    return {
        "material": format(material, "f"),
        "labor": format(labor, "f"),
        "total": format(normalized_total, "f"),
    }


def default_bdi_configuration() -> dict[str, Any]:
    result = deepcopy(BDI_TEMPLATE)
    for row in result["rows"]:
        row["values"] = {"percentage": "0.0000", "amount": "0.00"}
    result.update(
        {
            "configured": False,
            "calculated_percentage": "0.0000",
            "calculated_factor": "1.000000000000",
            "calculation_status": "NOT_CONFIGURED",
            "summary": {
                "direct_cost": _breakdown(),
                "indirect_cost": _breakdown(),
                "subtotal_cost": _breakdown(),
                "non_tax_percentage": "0.0000",
                "non_tax_amount": "0.00",
                "subtotal_sale": "0.00",
                "tax_percentage": "0.0000",
                "tax_amount": "0.00",
                "total_sale": "0.00",
            },
            "detail_total_percentage": "0.0000",
            "detail_total_amount": "0.00",
        }
    )
    return result


def default_di_configuration() -> dict[str, Any]:
    result = deepcopy(DI_TEMPLATE)
    for row in result["rows"]:
        row["values"] = {
            "quantity": "0.000000",
            "material": "0.0000",
            "labor": "0.0000",
            "unit_price": "0.0000",
            "total": "0.00",
        }
    for table in result["auxiliary_tables"]:
        table["configured"] = False
        for row in table["rows"]:
            row["values"] = {
                "quantity": "0.000000",
                "factor": _format4(Decimal(row.pop("factor", "1"))),
                "unit_price": _format4(Decimal(row.pop("unit_price", "0"))),
                "total": "0.00",
            }
        table["total"] = "0.00"
    result["configured"] = False
    result["totals"] = _breakdown()
    return result


def bdi_is_configured(sheet: BudgetSheet) -> bool:
    return bool((sheet.bdi_configuration or {}).get("configured"))


def _legacy_bdi_percentage(row: dict[str, Any], raw: dict[str, Any]) -> Any:
    values = row.get("values", {})
    if "percentage" in values:
        return values.get("percentage")
    active = raw.get("active_column", "intermediate")
    if active in values:
        return values.get(active)
    for key in ("intermediate", "final", "initial"):
        if key in values:
            return values.get(key)
    return "0"


def _merge_bdi_rows(current: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        _raise_field_error("bdi", "A configuração deve ser um objeto.")
    unexpected_top = set(payload) - {"rows"}
    if unexpected_top:
        _raise_field_error("bdi", f"Campos não permitidos: {', '.join(sorted(unexpected_top))}.")

    result = deepcopy(current)
    template_rows = {row["key"]: row for row in result["rows"]}
    payload_rows = payload.get("rows", [])
    if not isinstance(payload_rows, list):
        _raise_field_error("bdi.rows", "Informe uma lista de linhas.")

    for index, received in enumerate(payload_rows):
        if not isinstance(received, dict):
            _raise_field_error("bdi.rows", f"Linha {index + 1} inválida.")
        unexpected = set(received) - {"key", "values"}
        if unexpected:
            _raise_field_error(
                "bdi.rows",
                f"A linha {index + 1} contém campos estruturais não editáveis: {', '.join(sorted(unexpected))}.",
            )
        key = str(received.get("key") or "").strip()
        if key not in template_rows:
            _raise_field_error("bdi.rows", f"Linha desconhecida: {key or index + 1}.")
        values = received.get("values", {})
        if not isinstance(values, dict):
            _raise_field_error("bdi.rows", f"Valores inválidos na linha {key}.")
        unexpected_values = set(values) - {"percentage"}
        if unexpected_values:
            _raise_field_error(
                "bdi.rows",
                f"Colunas não editáveis/desconhecidas em {key}: {', '.join(sorted(unexpected_values))}.",
            )
        if "percentage" in values:
            template_rows[key]["values"]["percentage"] = _format4(
                _decimal(values["percentage"], field=f"bdi.{key}.percentage")
            )

    result["configured"] = True
    return result


def _merge_di_rows(current: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        _raise_field_error("di", "A configuração deve ser um objeto.")
    unexpected_top = set(payload) - {"rows", "auxiliary_tables"}
    if unexpected_top:
        _raise_field_error("di", f"Campos não permitidos: {', '.join(sorted(unexpected_top))}.")

    result = deepcopy(current)
    template_rows = {row["key"]: row for row in result["rows"]}
    payload_rows = payload.get("rows", [])
    if not isinstance(payload_rows, list):
        _raise_field_error("di.rows", "Informe uma lista de linhas.")

    for index, received in enumerate(payload_rows):
        if not isinstance(received, dict):
            _raise_field_error("di.rows", f"Linha {index + 1} inválida.")
        unexpected = set(received) - {"key", "values"}
        if unexpected:
            _raise_field_error(
                "di.rows",
                f"A linha {index + 1} contém campos estruturais não editáveis: {', '.join(sorted(unexpected))}.",
            )
        key = str(received.get("key") or "").strip()
        if key not in template_rows:
            _raise_field_error("di.rows", f"Linha desconhecida: {key or index + 1}.")
        target = template_rows[key]
        if target.get("row_type") != "ITEM":
            _raise_field_error("di.rows", f"A linha {target.get('item', key)} é um subtotal e não pode ser editada.")

        values = received.get("values", {})
        if not isinstance(values, dict):
            _raise_field_error("di.rows", f"Valores inválidos na linha {key}.")
        unexpected_values = set(values) - {"quantity", "material", "labor"}
        if unexpected_values:
            _raise_field_error(
                "di.rows",
                f"Colunas não editáveis/desconhecidas em {key}: {', '.join(sorted(unexpected_values))}.",
            )
        if "quantity" in values:
            target["values"]["quantity"] = _format6(
                _decimal(values["quantity"], field=f"di.{key}.quantity")
            )
        for column in ("material", "labor"):
            if column in values:
                target["values"][column] = _format4(
                    _decimal(values[column], field=f"di.{key}.{column}")
                )

    auxiliary_by_key = {table["key"]: table for table in result.get("auxiliary_tables", [])}
    received_tables = payload.get("auxiliary_tables", [])
    if not isinstance(received_tables, list):
        _raise_field_error("di.auxiliary_tables", "Informe uma lista de memórias auxiliares.")
    for table_index, received_table in enumerate(received_tables):
        if not isinstance(received_table, dict):
            _raise_field_error("di.auxiliary_tables", f"Tabela {table_index + 1} inválida.")
        unexpected = set(received_table) - {"key", "rows"}
        if unexpected:
            _raise_field_error("di.auxiliary_tables", "A memória auxiliar contém campos estruturais não editáveis.")
        table_key = str(received_table.get("key") or "")
        if table_key not in auxiliary_by_key:
            _raise_field_error("di.auxiliary_tables", f"Memória auxiliar desconhecida: {table_key}.")
        target_rows = {row["key"]: row for row in auxiliary_by_key[table_key]["rows"]}
        auxiliary_by_key[table_key]["configured"] = True
        for received_row in received_table.get("rows", []):
            row_key = str(received_row.get("key") or "")
            if row_key not in target_rows:
                _raise_field_error("di.auxiliary_tables", f"Linha auxiliar desconhecida: {row_key}.")
            values = received_row.get("values", {})
            if not isinstance(values, dict):
                _raise_field_error("di.auxiliary_tables", f"Valores inválidos em {row_key}.")
            unexpected_values = set(values) - {"quantity", "factor", "unit_price"}
            if unexpected_values:
                _raise_field_error("di.auxiliary_tables", f"Colunas desconhecidas em {row_key}.")
            target = target_rows[row_key]["values"]
            if "quantity" in values:
                target["quantity"] = _format6(_decimal(values["quantity"], field=f"di.{row_key}.quantity"))
            for column in ("factor", "unit_price"):
                if column in values:
                    target[column] = _format4(_decimal(values[column], field=f"di.{row_key}.{column}"))

    result["configured"] = True
    return result


def _calculate_di(config: dict[str, Any]) -> dict[str, Any]:
    main_rows = {row["key"]: row for row in config["rows"]}
    for table in config.get("auxiliary_tables", []):
        rows = table["rows"]
        role_quantities = {
            row.get("role"): Decimal(row["values"].get("quantity", "0") or "0")
            for row in rows if row.get("role")
        }
        table_total = ZERO
        for row in rows:
            values = row["values"]
            quantity = Decimal(values.get("quantity", "0") or "0")
            factor = Decimal(values.get("factor", "1") or "1")
            unit_price = Decimal(values.get("unit_price", "0") or "0")
            if table["calculation"] == "TRANSPORT" and row.get("role") == "FARE":
                raw_total = quantity * unit_price * role_quantities.get("PEOPLE", ZERO) * role_quantities.get("RIDES", ZERO) * role_quantities.get("PERIOD", ZERO)
            elif row.get("role"):
                raw_total = ZERO
            else:
                raw_total = quantity * factor * unit_price
            line_total = _money2(raw_total)
            values["total"] = format(line_total, "f")
            table_total += line_total
        table["total"] = _money_string(table_total)
        target = table.get("target")
        if table.get("configured") and target and target["row"] in main_rows:
            main_rows[target["row"]]["values"][target["column"]] = _format4(_money2(table_total))

    group_raw: dict[str, dict[str, Decimal]] = {}
    grand_material_raw = ZERO
    grand_labor_raw = ZERO
    grand_total = ZERO

    for row in config["rows"]:
        values = row["values"]
        if row.get("row_type") != "ITEM":
            continue

        quantity = Decimal(values.get("quantity", "0") or "0")
        material_unit = Decimal(values.get("material", "0") or "0")
        labor_unit = Decimal(values.get("labor", "0") or "0")
        unit_price = material_unit + labor_unit

        material_line_raw = quantity * material_unit
        labor_line_raw = quantity * labor_unit
        total_line = _money2(quantity * unit_price)

        values["unit_price"] = _format4(unit_price)
        values["total"] = format(total_line, "f")

        group = row.get("group") or ""
        aggregate = group_raw.setdefault(
            group,
            {"material": ZERO, "labor": ZERO, "total": ZERO},
        )
        aggregate["material"] += material_line_raw
        aggregate["labor"] += labor_line_raw
        aggregate["total"] += total_line

    for row in config["rows"]:
        if row.get("row_type") != "GROUP":
            continue
        aggregate = group_raw.get(
            row.get("group") or "",
            {"material": ZERO, "labor": ZERO, "total": ZERO},
        )
        material = _money2(aggregate["material"])
        labor = _money2(aggregate["labor"])
        total = _money2(aggregate["total"])
        row["values"] = {
            "quantity": "0.000000",
            "material": _format4(material),
            "labor": _format4(labor),
            "unit_price": "0.0000",
            "total": format(total, "f"),
        }
        # F140/G140 somam os SUMPRODUCTs dos grupos sem arredondar cada
        # subtotal exibido. Arredondar grupo a grupo causava diferença de R$0,02.
        grand_material_raw += aggregate["material"]
        grand_labor_raw += aggregate["labor"]
        grand_total += total

    # F140/G140 do Excel alimentam o BDI sem arredondar; I140 soma linhas arredondadas.
    config["calculation_totals"] = {
        "material": format(grand_material_raw, "f"),
        "labor": format(grand_labor_raw, "f"),
        "total": format(grand_material_raw + grand_labor_raw, "f"),
    }
    config["totals"] = _breakdown(
        _money2(grand_material_raw),
        _money2(grand_labor_raw),
        grand_total,
    )
    return config


def _rate(rows: dict[str, dict[str, str]], key: str) -> Decimal:
    return Decimal(rows[key].get("percentage", "0") or "0") / HUNDRED


def _rate_sum(rows: dict[str, dict[str, str]], keys: tuple[str, ...]) -> Decimal:
    return sum((_rate(rows, key) for key in keys), ZERO)


def _calculate_bdi(
    config: dict[str, Any],
    *,
    direct_cost: dict[str, Decimal] | None = None,
    di_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calcula a memória B.D.I. com gross-up sobre D (referência PC25017).

    A = custo direto
    B = custo indireto (D.I.)
    C = A + B
    D = C * soma(Lucro + Imprevistos + Comercial + Seguros +
                  Reserva Técnica + Administração Central)
    E = C + D
    F = D / (1 - impostos) - D
    G = E + F
    Fator BDI = G / A

    Observação importante do Excel: ENCARGOS FINANCEIROS aparece na memória
    detalhada, mas não participa do SUM que forma D16.
    """
    rows = {row["key"]: row["values"] for row in config["rows"]}
    direct = direct_cost or {"material": ZERO, "labor": ZERO, "total": ZERO}
    di = di_config or default_di_configuration()
    indirect_totals = di.get("calculation_totals") or di.get("totals", {})

    direct_material = _money2(direct.get("material", ZERO))
    direct_labor = _money2(direct.get("labor", ZERO))
    direct_total = _money2(direct.get("total", direct_material + direct_labor))
    indirect_material = Decimal(indirect_totals.get("material", "0") or "0")
    indirect_labor = Decimal(indirect_totals.get("labor", "0") or "0")
    indirect_total = Decimal(indirect_totals.get("total", "0") or "0")

    subtotal_material = direct_material + indirect_material
    subtotal_labor = direct_labor + indirect_labor
    subtotal_total = direct_total + indirect_total

    non_tax_rate = _rate_sum(rows, BDI_NON_TAX_KEYS)
    tax_rate = _rate_sum(rows, BDI_TAX_KEYS)
    if tax_rate >= ONE:
        _raise_field_error(
            "bdi.impostos",
            "A soma dos impostos deve ser inferior a 100% para calcular o BDI.",
        )

    non_tax_amount = subtotal_total * non_tax_rate
    subtotal_sale = subtotal_total + non_tax_amount
    # PC25017, G18: o gross-up incide somente sobre D.
    # O D.I. já integra C e, portanto, a base usada para calcular D.
    tax_amount = non_tax_amount / (ONE - tax_rate) - non_tax_amount
    total_sale = subtotal_sale + tax_amount

    if direct_total > ZERO:
        factor = total_sale / direct_total
        percentage = (factor - ONE) * HUNDRED
        status = "CALCULATED"
    else:
        factor = ONE
        percentage = ZERO
        status = "WAITING_DIRECT_COST" if config.get("configured") else "NOT_CONFIGURED"

    detail_total_percentage = ZERO
    detail_total_amount = ZERO
    for row in config["rows"]:
        values = row["values"]
        rate = Decimal(values.get("percentage", "0") or "0") / HUNDRED
        # Na memória detalhada do Excel, LUCRO é calculado sobre C; as demais
        # linhas são demonstradas sobre o valor de D.
        amount = subtotal_total * rate if row["key"] == "lucro" else non_tax_amount * rate
        values["amount"] = _money_string(amount)
        detail_total_percentage += Decimal(values.get("percentage", "0") or "0")
        detail_total_amount += amount

    config["calculated_percentage"] = _format4(percentage)
    config["calculated_factor"] = format(
        factor.quantize(FACTOR_12, rounding=ROUND_HALF_UP),
        "f",
    )
    config["calculation_status"] = status
    config["summary"] = {
        "direct_cost": _breakdown(direct_material, direct_labor, direct_total),
        "indirect_cost": _breakdown(indirect_material, indirect_labor, indirect_total),
        "subtotal_cost": _breakdown(subtotal_material, subtotal_labor, subtotal_total),
        "non_tax_percentage": _format4(non_tax_rate * HUNDRED),
        "non_tax_amount": _money_string(non_tax_amount),
        "subtotal_sale": _money_string(subtotal_sale),
        "tax_percentage": _format4(tax_rate * HUNDRED),
        "tax_amount": _money_string(tax_amount),
        "total_sale": _money_string(total_sale),
    }
    config["detail_total_percentage"] = _format4(detail_total_percentage)
    config["detail_total_amount"] = _money_string(detail_total_amount)
    return config


def normalize_di_configuration(raw: dict[str, Any] | None) -> dict[str, Any]:
    base = default_di_configuration()
    if not raw:
        return base

    # V3 é a primeira estrutura fiel à tabela principal da guia D.I.
    # Memórias V1/V2 resumiam grupos e não possuem dados suficientes para
    # reconstruir Quantidade/Material/Mão de obra sem inventar distribuição.
    # Portanto não as aplicamos silenciosamente ao novo cálculo.
    if int(raw.get("version") or 0) < 3:
        base["legacy_configuration_detected"] = True
        base["legacy_configuration_message"] = (
            "A memória D.I. anterior usava uma estrutura resumida incompatível "
            "com a tabela analítica atual. Revise e salve novamente esta revisão."
        )
        return base

    payload_rows = []
    for row in raw.get("rows", []):
        if not isinstance(row, dict) or not row.get("key"):
            continue

        # A memória persistida contém também as colunas calculadas
        # ``unit_price`` e ``total``. Elas são read-only no contrato de
        # escrita e, portanto, não podem ser reenviadas para _merge_di_rows
        # durante a normalização. Reaproveitamos somente os três valores
        # que representam entrada do usuário; os calculados são sempre
        # reconstruídos por _calculate_di().
        stored_values = row.get("values", {})
        if not isinstance(stored_values, dict):
            stored_values = {}
        editable_values = {
            key: stored_values[key]
            for key in ("quantity", "material", "labor")
            if key in stored_values
        }
        payload_rows.append({"key": row["key"], "values": editable_values})

    known_items = {row["key"] for row in base["rows"] if row.get("row_type") == "ITEM"}
    payload_rows = [row for row in payload_rows if row["key"] in known_items]
    auxiliary_tables = []
    for table in raw.get("auxiliary_tables", []):
        if not isinstance(table, dict) or not table.get("key"):
            continue
        rows = []
        for row in table.get("rows", []):
            if not isinstance(row, dict) or not row.get("key"):
                continue
            values = row.get("values", {}) if isinstance(row.get("values"), dict) else {}
            rows.append({"key": row["key"], "values": {key: values[key] for key in ("quantity", "factor", "unit_price") if key in values}})
        auxiliary_tables.append({"key": table["key"], "rows": rows})
    merged = _merge_di_rows(base, {"rows": payload_rows, "auxiliary_tables": auxiliary_tables})
    merged["configured"] = bool(raw.get("configured", True))
    return _calculate_di(merged)


def normalize_bdi_configuration(
    raw: dict[str, Any] | None,
    *,
    direct_cost: dict[str, Decimal] | None = None,
    di_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = default_bdi_configuration()
    if not raw:
        return base

    payload_rows = []
    for row in raw.get("rows", []):
        if not isinstance(row, dict) or not row.get("key"):
            continue
        source_key = str(row["key"])
        target_key = BDI_LEGACY_KEY_ALIASES.get(source_key, source_key)
        payload_rows.append(
            {
                "key": target_key,
                "values": {"percentage": _legacy_bdi_percentage(row, raw)},
            }
        )

    known = {row["key"] for row in base["rows"]}
    payload_rows = [row for row in payload_rows if row["key"] in known]
    merged = _merge_bdi_rows(base, {"rows": payload_rows})
    merged["configured"] = bool(raw.get("configured", True))
    return _calculate_bdi(merged, direct_cost=direct_cost, di_config=di_config)


def budget_sheet_direct_cost_breakdown(sheet: BudgetSheet) -> dict[str, Decimal]:
    """Retorna A separado em Material/Mão de obra/Total.

    A planilha de referência possui apenas Material e Mão de obra. Para manter
    essa mesma apresentação, equipamento e eventual resíduo de composição são
    agrupados em Material. Insumos diretos do tipo LABOR vão para Mão de obra;
    os demais tipos vão para Material.
    """
    material = ZERO
    labor = ZERO
    items = BudgetSheetStageItem.objects.filter(
        budget_sheet_stage__budget_sheet=sheet
    ).values(
        "item_type",
        "quantity",
        "unit_cost",
        "unit_price",
        "material_unit_cost",
        "labor_unit_cost",
        "equipment_unit_cost",
        "supply__supply_type",
    )

    for item in items:
        quantity = Decimal(item["quantity"] or 0)
        if item["item_type"] == BudgetSheetItemType.SERVICE_COMPOSITION:
            line_total = _money2(quantity * Decimal(item["unit_cost"] or 0))
            line_material = _money2(
                quantity
                * (
                    Decimal(item["material_unit_cost"] or 0)
                    + Decimal(item["equipment_unit_cost"] or 0)
                )
            )
            line_labor = _money2(quantity * Decimal(item["labor_unit_cost"] or 0))
            residual = line_total - line_material - line_labor
            line_material += residual
            material += line_material
            labor += line_labor
        else:
            base = item["unit_cost"] if item["item_type"] == BudgetSheetItemType.SUPPLY else item["unit_price"]
            line_total = _money2(quantity * Decimal(base or 0))
            if item.get("supply__supply_type") == SupplyType.LABOR:
                labor += line_total
            else:
                material += line_total

    material = _money2(material)
    labor = _money2(labor)
    return {"material": material, "labor": labor, "total": _money2(material + labor)}


def budget_sheet_direct_cost(sheet: BudgetSheet) -> Decimal:
    return budget_sheet_direct_cost_breakdown(sheet)["total"]


def calculated_bdi_configuration(sheet: BudgetSheet) -> dict[str, Any]:
    di_config = normalize_di_configuration(sheet.di_configuration)
    return normalize_bdi_configuration(
        sheet.bdi_configuration,
        direct_cost=budget_sheet_direct_cost_breakdown(sheet),
        di_config=di_config,
    )


def refresh_budget_sheet_bdi(sheet: BudgetSheet) -> Decimal:
    if not bdi_is_configured(sheet):
        percentage = ZERO
        if Decimal(sheet.bdi_percentage or 0) != percentage:
            BudgetSheet.objects.filter(pk=sheet.pk).update(bdi_percentage=percentage)
            sheet.bdi_percentage = percentage
        return percentage

    calculated = calculated_bdi_configuration(sheet)
    percentage = Decimal(calculated["calculated_percentage"])

    changed_fields: dict[str, Any] = {}
    if sheet.bdi_configuration != calculated:
        changed_fields["bdi_configuration"] = calculated
        sheet.bdi_configuration = calculated
    if Decimal(sheet.bdi_percentage or 0) != percentage:
        changed_fields["bdi_percentage"] = percentage
        sheet.bdi_percentage = percentage
    if changed_fields:
        BudgetSheet.objects.filter(pk=sheet.pk).update(**changed_fields)
    return percentage


def get_budget_cost_configuration(sheet: BudgetSheet) -> dict[str, Any]:
    di_config = normalize_di_configuration(sheet.di_configuration)
    bdi_config = normalize_bdi_configuration(
        sheet.bdi_configuration,
        direct_cost=budget_sheet_direct_cost_breakdown(sheet),
        di_config=di_config,
    )
    return {
        "budget_sheet_id": sheet.pk,
        "revision": sheet.revision,
        "bdi": bdi_config,
        "di": di_config,
    }


@transaction.atomic
def save_budget_cost_configuration(
    budget_sheet_id: int,
    payload: dict[str, Any],
    *,
    user=None,
) -> dict[str, Any]:
    sheet = BudgetSheet.objects.select_for_update().get(pk=budget_sheet_id)
    ensure_budget_sheet_editable(sheet)
    actor = user if getattr(user, "pk", None) else None
    updates: list[str] = []

    if "di" in payload:
        current_di = normalize_di_configuration(sheet.di_configuration)
        merged_di = _merge_di_rows(current_di, payload["di"] or {})
        sheet.di_configuration = _calculate_di(merged_di)
        updates.append("di_configuration")

    if "bdi" in payload:
        current_di = normalize_di_configuration(sheet.di_configuration)
        current_bdi = normalize_bdi_configuration(
            sheet.bdi_configuration,
            direct_cost=budget_sheet_direct_cost_breakdown(sheet),
            di_config=current_di,
        )
        merged_bdi = _merge_bdi_rows(current_bdi, payload["bdi"] or {})
        merged_bdi = _calculate_bdi(
            merged_bdi,
            direct_cost=budget_sheet_direct_cost_breakdown(sheet),
            di_config=current_di,
        )
        sheet.bdi_configuration = merged_bdi
        sheet.bdi_percentage = Decimal(merged_bdi["calculated_percentage"])
        updates.extend(["bdi_configuration", "bdi_percentage"])

    if not updates:
        raise ValidationError("Informe bdi e/ou di para salvar a configuração.")

    # As memórias BDI/D.I. já foram validadas e normalizadas acima.
    # Não use model.save() aqui: BudgetSheet.save() executa full_clean() de
    # todo o agregado e acabava rejeitando a memória D.I. analítica durante
    # a persistência, devolvendo HTTP 400 mesmo para payloads válidos.
    # QuerySet.update() persiste somente os campos calculados por este serviço
    # e mantém as validações de domínio concentradas neste fluxo.
    update_values: dict[str, Any] = {
        field: getattr(sheet, field)
        for field in dict.fromkeys(updates)
    }
    update_values["updated_by"] = actor
    update_values["updated_at"] = timezone.now()
    BudgetSheet.objects.filter(pk=sheet.pk).update(**update_values)

    sheet.updated_by = actor

    from budgeting.services.budget_sheets import recalculate_budget_totals

    if bdi_is_configured(sheet):
        recalculate_budget_totals(sheet.pk)

    sheet.refresh_from_db()
    return get_budget_cost_configuration(sheet)
