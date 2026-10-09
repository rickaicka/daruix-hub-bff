"""Identidade visual comum aos exportadores, baseada no XLS PC25017.

Os nomes descrevem a função visual. Não participam do cálculo de BDI/DI.
"""
from pathlib import Path


COMPANY = 'R.S. DARUIX ENGENHARIA LTDA.'
MAIN_LOGO_PATH = Path(__file__).resolve().parent.parent / 'assets' / 'daruix-main-logo.png'
HUB_LOGO_PATH = Path(__file__).resolve().parent.parent / 'assets' / 'daruix-hub-footer-logo.png'
HUB_FOOTER_SMALL_PATH = Path(__file__).resolve().parent.parent / 'assets' / 'daruix-hub-footer-logo-small.png'
PALETTE = {
    'white': '#FFFFFF',
    'gray': '#DDDDDD',
    'cyan': '#CCFFFF',
    'yellow': '#FFFFCC',
    'green': '#CCFFCC',
    'lime': '#99FF33',
    'pink': '#FFDDFF',
    'red': '#FF0000',
    'blue': '#0000FF',
}
TABLE_HEADER_ROW = 9  # zero-based; rows 1:9 hold the original-style header.
BDI_FACTOR_CELL = '$B$17'
BDI_TAX_HIGHLIGHTS = frozenset({
    'ir_imposto_renda_lucro', 'cs_contribuicao_social_lucro', 'pis', 'cofins',
    'diferencas_impostos', 'imposto_sobre_lucro',
})
DI_AUXILIARY_ROWS = frozenset({'01_09', '01_10', '01_11', '01_12', '01_13'})
DI_PAYROLL_ROWS = frozenset({'04_01', '04_02', '04_03', '04_04', '04_05', '04_06', '04_07'})


def heading_lines(data):
    """Dados do orçamento corrente; nunca reaproveita dados fixos do XLS modelo."""
    project = data.get('work_name') or ''
    code = data.get('proposal_code') or data['number']
    return [
        f'{code} - {project}' if project else code,
        f"Cliente: {data.get('party_name') or 'Não informado'}",
        f"Local: {data.get('work_location') or 'Não informado'}",
        f"Serviços: {data.get('services_name') or project or 'Não informado'}",
        f'Empresa: {COMPANY}',
        f"Data: {data['date']}",
        f"REVISÃO Nº {int(data['revision']):02d}   |   Orçamento: {data['number']}"
        + ('   |   USO INTERNO DARUIX' if data['audience'] == 'DARUIX' else ''),
    ]


def work_location(proposal, work):
    """Campos opcionais da obra/proposta; não usa o endereço cadastral do cliente.

    Mantém compatibilidade com instalações sem cadastro de endereço da obra.
    Objetos relacionados não são convertidos em texto como se fossem endereços.
    """
    for obj, fields in (
        (work, ('full_address', 'address', 'location')),
        (proposal, ('work_address', 'work_location')),
    ):
        for field in fields:
            value = getattr(obj, field, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ''


def di_cell_tone(row, field):
    if row.get('row_type') == 'GROUP':
        return 'green'
    key = row['key']
    if key in DI_AUXILIARY_ROWS and field in ('item', 'description', 'unit', 'material', 'labor'):
        return 'pink'
    if field == 'quantity':
        return 'yellow'
    if field == 'labor' and key in DI_PAYROLL_ROWS:
        return 'lime'
    if field in ('material', 'labor', 'unit_price'):
        return 'cyan'
    return 'white'
