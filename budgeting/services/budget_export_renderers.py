"""Renderização de um contrato explícito: cliente nunca recebe o bloco interno."""
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from math import ceil
from xml.sax.saxutils import escape
from .budget_export_branding import (
    COMPANY, MAIN_LOGO_PATH, HUB_LOGO_PATH, HUB_FOOTER_SMALL_PATH, PALETTE, TABLE_HEADER_ROW, BDI_FACTOR_CELL,
    BDI_TAX_HIGHLIGHTS, heading_lines, di_cell_tone,
)

ZERO = Decimal('0')


def dec(value):
    return Decimal(str(value or 0))


def money(value):
    return dec(value).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def br(value, places=2):
    return f'{dec(value):,.{places}f}'.replace(',', '@').replace('.', ',').replace('@', '.')


def items(data):
    for stage in data['stages']:
        yield from stage['items']


def component_rows(item):
    """Detalhes do snapshot vigente, em ordem hierárquica, sem duplicar vendas."""
    components = item['cost'].get('components', [])
    disabled = {str(c.get('source_path')) for c in components
                if c.get('enabled', True) is False and c.get('source_path')}
    for index, component in enumerate(components, 1):
        path = str(component.get('source_path') or index)
        if component.get('enabled', True) is False or any(
            path == ancestor or path.startswith(ancestor + '.') for ancestor in disabled
        ):
            continue
        material = dec(component.get('material_unit_price'))
        labor = dec(component.get('labor_unit_price'))
        equipment = dec(component.get('equipment_unit_price'))
        yield {
            'number': f"{item['number']}.{path}",
            'description': component.get('description_snapshot') or '',
            'unit': component.get('unit_snapshot') or '',
            'quantity': dec(item['quantity']) * dec(component.get('coefficient')),
            'depth': len(path.split('.')),
            'group': bool(component.get('display_only')),
            'cost': {'material': material, 'labor': labor,
                     'unit_cost': dec(component.get('unit_cost', material + labor + equipment))},
        }


PLANILHA_COST_HEADERS = [
    'CUSTO UNIT. MATERIAL', 'CUSTO UNIT. MÃO DE OBRA', 'CUSTO UNIT. TOTAL',
    'CUSTO TOTAL MATERIAL', 'CUSTO TOTAL MÃO DE OBRA', 'CUSTO TOTAL',
]


def _write_planilha_cost(ws, row, item, f):
    n = row + 1
    for col, key in [(6, 'material'), (7, 'labor'), (8, 'unit_cost')]:
        ws.write_number(row, col, float(dec(item['cost'][key])), f['money'])
    for col, letter, key in [(9, 'G', 'material'), (10, 'H', 'labor'), (11, 'I', 'unit_cost')]:
        _formula(ws, row, col, f'=ROUND(D{n}*{letter}{n},2)', f['money'],
                 money(dec(item['quantity']) * dec(item['cost'][key])))


def _formats(wb):
    base = {'font_name': 'Arial', 'font_size': 9, 'valign': 'vcenter'}
    def fmt(**kw): return wb.add_format({**base, **kw})
    return {
        'title': fmt(bold=True, font_size=14, font_color='#C00D0E'),
        'text': fmt(text_wrap=True),
        'cell': fmt(border=1, text_wrap=True),
        'head': fmt(bold=True, border=1, bg_color=PALETTE['gray'], text_wrap=True, align='center'),
        'group': fmt(bold=True, border=1, bg_color=PALETTE['gray'], text_wrap=True),
        'money': fmt(border=1, num_format='#,##0.00'),
        'qty': fmt(border=1, num_format='0.######'),
        'factor': fmt(border=1, num_format='0.000000000000'),
        'total': fmt(bold=True, border=1, bg_color=PALETTE['gray'], num_format='#,##0.00'),
        **{f'{tone}_{kind}': fmt(bg_color=color, border=1, text_wrap=True,
                               bold=kind in ('head', 'total', 'group'),
                               align='center' if kind == 'head' else 'right' if kind in ('money', 'qty', 'factor', 'total') else 'left',
                               num_format='0.000000000000' if kind == 'factor' else '0.######' if kind == 'qty' else '#,##0.00' if kind in ('money', 'total') else '@')
           for tone, color in PALETTE.items() if tone not in ('red', 'blue')
           for kind in ('cell', 'head', 'group', 'money', 'qty', 'factor', 'total')},
        'bdi_input': fmt(border=1, bg_color=PALETTE['green'], font_color=PALETTE['red'], num_format='0.0000'),
    }


def _setup(ws, last_col, last_row, header=TABLE_HEADER_ROW, a3=False):
    ws.freeze_panes(header + 1, 2)
    ws.repeat_rows(0, header)
    ws.set_landscape()
    ws.set_paper(8 if a3 else 9)
    ws.fit_to_pages(1, 0)
    ws.set_margins(.25, .25, .45, .45)
    ws.print_area(0, 0, last_row, last_col)
    # O Excel usa o tamanho físico do PNG no footer. Por isso existe uma versão
    # reduzida exclusiva para o rodapé, evitando que o logo invada a área útil.
    ws.set_footer(
        f'&L {COMPANY}&C Página &P de &N&R&G',
        {'image_right': str(HUB_FOOTER_SMALL_PATH), 'margin': 0.16},
    )
    ws.hide_gridlines(2)


def _heading(ws, data, f, title, last=5, tone='gray'):
    """Cabeçalho com logo principal à esquerda, identificação da obra à direita e faixa de título."""
    from PIL import Image
    background = PALETTE[tone] if tone in ('cyan', 'yellow') else PALETTE['white']
    wb = f['workbook']
    normal = wb.add_format({'font_name': 'Arial', 'font_size': 10, 'valign': 'vcenter',
                            'text_wrap': True, 'bg_color': background})
    highlight = wb.add_format({'font_name': 'Arial', 'font_size': 11, 'bold': True,
                               'font_color': PALETTE['red'], 'valign': 'vcenter',
                               'text_wrap': True, 'bg_color': background})
    widths = f['column_widths'][ws.name]
    pixels = [int(w * 7 + 5) for w in widths]
    # Reserva aproximadamente 30% do cabeçalho para o logo e 70% para os dados.
    # O logo fica centralizado no seu bloco e o texto recebe o mesmo respiro lateral.
    total_width = sum(pixels[:last + 1])
    target_logo_width = max(220, int(total_width * 0.30))
    text_start = 1
    logo_area_width = pixels[0]
    while text_start < max(2, last - 2) and logo_area_width < target_logo_width:
        logo_area_width += pixels[text_start]
        text_start += 1
    text_start = max(2, min(text_start, last - 1))
    logo_area_width = sum(pixels[:text_start])
    text_width = sum(pixels[text_start:last + 1])
    for r in range(7):
        ws.merge_range(r, 0, r, text_start - 1, '', normal)
    for r, text in enumerate(heading_lines(data)):
        fmt = highlight if r in (0, 6) else normal
        ws.merge_range(r, text_start, r, last, text, fmt)
        lines = sum(max(1, ceil(len(line) * 7 / max(text_width - 24, 1))) for line in text.splitlines())
        ws.set_row(r, max(21, 15 * lines + 6))
    with Image.open(MAIN_LOGO_PATH) as logo:
        iw, ih = logo.size
    max_logo_w = max(1, logo_area_width - 36)
    max_logo_h = 82
    scale = min(max_logo_w / max(iw, 1), max_logo_h / max(ih, 1))
    rendered_w = iw * scale
    rendered_h = ih * scale
    x_offset = max(0, int((logo_area_width - rendered_w) / 2))
    # Linhas 1:7 costumam somar ~147 px; centralizamos visualmente no bloco.
    header_px = 147
    y_offset = max(4, int((header_px - rendered_h) / 2))
    ws.insert_image(0, 0, str(MAIN_LOGO_PATH), {
        'x_scale': scale, 'y_scale': scale, 'x_offset': x_offset, 'y_offset': y_offset,
        'object_position': 1, 'description': 'Logo principal Daruix',
    })
    if ws.name == 'Planilha' and data['audience'] == 'DARUIX':
        factor_format = wb.add_format({'font_name': 'Arial', 'font_size': 10,
            'bold': True, 'align': 'right', 'valign': 'vcenter', 'num_format': '"Fator BDI: "0.000000',
            'bg_color': background})
        ws.merge_range(7, text_start, 7, last, '', factor_format)
        _formula(ws, 7, text_start, f"='BDI'!{BDI_FACTOR_CELL}", factor_format,
                 data['bdi'].get('calculated_factor', 1))
        ws.set_row(7, 21)
    else:
        ws.set_row(7, 8)
    ws.merge_range(8, 0, 8, last, title, f[f'{tone}_head'])
    ws.set_row(8, 27)


def _columns(ws, f, widths):
    f['column_widths'][ws.name] = widths
    for c, width in enumerate(widths):
        ws.set_column(c, c, width)


def _formula(ws, r, c, formula, fmt, cached):
    ws.write_formula(r, c, formula, fmt, float(dec(cached)))


def _sumrefs(col, rows):
    if not rows:
        return '0'
    ranges = []
    start = previous = rows[0]
    for row in rows[1:]:
        if row == previous + 1:
            previous = row
            continue
        ranges.append(f'{col}{start}:{col}{previous}' if previous > start else f'{col}{start}')
        start = previous = row
    ranges.append(f'{col}{start}:{col}{previous}' if previous > start else f'{col}{start}')
    return 'SUM(' + ','.join(ranges) + ')'



def render_xlsx(data):
    import xlsxwriter
    out = BytesIO()
    wb = xlsxwriter.Workbook(out, {'in_memory': True, 'strings_to_formulas': False, 'strings_to_urls': False})
    wb.set_properties({'title': f"Orçamento {data['number']}", 'author': 'R.S. DARUIX ENGENHARIA LTDA.'})
    f = _formats(wb)
    f.update(workbook=wb, column_widths={})
    ws = wb.add_worksheet('Planilha')
    internal = data['audience'] == 'DARUIX'
    headers = ['ITEM', 'DISCRIMINAÇÃO', 'UN.', 'QUANT.', 'PREÇO UNITÁRIO (R$)', 'TOTAL (R$)']
    if internal:
        headers += PLANILHA_COST_HEADERS
    _columns(ws, f, [9, 68, 8, 12] + [17] * (len(headers) - 4))
    _heading(ws, data, f, 'PLANILHA ORÇAMENTÁRIA', len(headers) - 1)
    ws.write_row(TABLE_HEADER_ROW, 0, headers, f['head']); ws.set_row(TABLE_HEADER_ROW, 48)
    r = TABLE_HEADER_ROW + 1; stage_totals = []; item_refs = {}
    for stage in data['stages']:
        stage_row = r
        stage_label = f"Etapa {stage['number']} - {stage['name']} - Total da Etapa"
        ws.merge_range(stage_row, 0, stage_row, 4, stage_label, f['group'])
        ws.set_row(stage_row, 28)
        rows = []
        r += 1
        for item in stage['items']:
            n = r+1; rows.append(n); item_refs[item['number']] = n
            ws.write_row(r, 0, [item['number'], item['description'], item['unit']], f['cell'])
            ws.write_number(r, 3, float(dec(item['quantity'])), f['qty'])
            # Preços finais persistidos: não transportar fórmulas ou metadados internos ao cliente.
            ws.write_number(r, 4, float(dec(item['unit_price'])), f['money'])
            ws.write_number(r, 5, float(dec(item['total'])), f['money'])
            ws.set_row(r, max(30, 14 * ceil(len(item['description'])/62)))
            if internal:
                _write_planilha_cost(ws, r, item, f)
            r += 1
            if internal:
                for child in component_rows(item):
                    ws.write_row(r, 0, [child['number'], child['description'], child['unit']], f['cell'])
                    indent = min(child['depth'], 15)
                    child_format = wb.add_format({'font_name': 'Arial', 'font_size': 9,
                        'border': 1, 'text_wrap': True, 'valign': 'vcenter', 'indent': indent,
                        'bold': child['group'], 'bg_color': PALETTE['green'] if child['group'] else '#F7F7FC'})
                    ws.write(r, 1, child['description'], child_format)
                    ws.write_number(r, 3, float(child['quantity']), f['qty'])
                    # E/F são vendas salvas apenas na linha principal. Não inventa venda dos filhos.
                    for col in (4, 5):
                        ws.write_blank(r, col, None, f['cell'])
                    _write_planilha_cost(ws, r, child, f)
                    ws.set_row(r, max(30, 14 * ceil((len(child['description']) + indent * 3) / 62)))
                    r += 1
        if internal:
            _formula(ws,stage_row,5,'='+_sumrefs('F',rows),f['total'],stage['total'])
            for c,letter,key in [(9,'J','material'),(10,'K','labor'),(11,'L','unit_cost')]:
                val = sum((money(dec(i['quantity'])*dec(i['cost'][key])) for i in stage['items']),ZERO)
                _formula(ws,stage_row,c,'='+_sumrefs(letter,rows),f['total'],val)
        else:
            ws.write_number(stage_row,5,float(dec(stage['total'])),f['total'])
        stage_totals.append(stage_row+1)
    ws.merge_range(r,0,r,4,'TOTAL GERAL',f['group'])
    if internal:
        _formula(ws,r,5,'='+_sumrefs('F',stage_totals),f['total'],data['total'])
        for c,letter,key in [(9,'J','material'),(10,'K','labor'),(11,'L','unit_cost')]:
            val=sum((money(dec(i['quantity'])*dec(i['cost'][key])) for i in items(data)),ZERO)
            _formula(ws,r,c,'='+_sumrefs(letter,stage_totals),f['total'],val)
    else: ws.write_number(r,5,float(dec(data['total'])),f['total'])
    total_row = r+1
    if internal:
        r+=2; ws.merge_range(r,0,r,11,'Preços E/F são as vendas salvas no Hub nas linhas principais. Componentes mostram custos; os totais das etapas não somam novamente os detalhes.',f['text'])
        ws.set_row(r,30)
        _write_di(wb,data,f)
        _write_bdi(wb,data,f,total_row)
        _write_components(wb,data,f,item_refs)
    _setup(ws,len(headers)-1,r,a3=internal)
    wb.close()
    return out.getvalue()


def _write_di(wb,data,f):
    f = {**f, 'head': f['cyan_head'], 'group': f['green_group'], 'total': f['green_total']}
    aux=wb.add_worksheet('DI Auxiliares');aux.write_row(TABLE_HEADER_ROW,0,['MEMÓRIA','ITEM','DISCRIMINAÇÃO','QTD.','FATOR','UNITÁRIO','TOTAL'],f['head'])
    _columns(aux, f, [12, 12, 55, 16, 16, 16, 16])
    _heading(aux, data, f, 'DESPESAS INDIRETAS - MEMÓRIAS AUXILIARES', 6, 'cyan')
    a=TABLE_HEADER_ROW + 1; targets={}
    for table in data['di'].get('auxiliary_tables',[]):
        aux.merge_range(a,0,a,6,table.get('title') or table.get('discrimination') or table['key'],f['pink_head']);a+=1
        roles={row.get('role'):a+idx+1 for idx,row in enumerate(table['rows']) if row.get('role')}
        first=a+1; value_total=ZERO
        for row in table['rows']:
            n=a+1;v=row['values'];q=dec(v.get('quantity'));factor=dec(v.get('factor',1));price=dec(v.get('unit_price'))
            aux.write_row(a,0,[table.get('item',table['key']),row['key'],row.get('discrimination') or row.get('label') or row['key']],f['cell'])
            for c,num in [(3,q),(4,factor),(5,price)]:aux.write_number(a,c,float(num),f['yellow_qty'] if c<5 else f['cyan_money'])
            if table.get('calculation')=='TRANSPORT' and row.get('role')=='FARE':
                refs=[f'D{roles[role]}' if role in roles else '0' for role in ('PEOPLE','RIDES','PERIOD')]
                formula=f'=ROUND(D{n}*F{n}*'+ '*'.join(refs)+',2)'
            elif row.get('role'):formula='=0'
            else:formula=f'=ROUND(D{n}*E{n}*F{n},2)'
            cached=dec(v.get('total'));value_total+=cached
            _formula(aux,a,6,formula,f['money'],cached);aux.set_row(a,30);a+=1
        aux.merge_range(a,0,a,5,'TOTAL DA MEMÓRIA',f['group'])
        _formula(aux,a,6,f'=SUM(G{first}:G{a})' if a>=first else '=0',f['total'],value_total)
        if table.get('configured') and table.get('target'):
            t=table['target'];targets[(t['row'],t['column'])]=a+1
        a+=2
    _setup(aux,6,max(a,TABLE_HEADER_ROW + 1))
    ws=wb.add_worksheet('DI')
    ws.write_row(TABLE_HEADER_ROW,0,['ITEM','DISCRIMINAÇÃO','UN.','QUANT.','MATERIAL UNIT.','MÃO DE OBRA UNIT.','UNITÁRIO TOTAL','TOTAL ARREDONDADO','MATERIAL TOTAL SEM ARRED.','M.O. TOTAL SEM ARRED.'],f['head'])
    _columns(ws, f, [10, 58, 10, 10] + [18] * 6)
    _heading(ws, data, f, 'DESPESAS INDIRETAS', 9, 'cyan')
    ws.set_row(TABLE_HEADER_ROW,38)
    r=TABLE_HEADER_ROW + 1;leaf_rows=[];groups={};group_headers=[]
    for row in data['di']['rows']:
        v=row['values'];n=r+1
        if row.get('row_type')=='GROUP':
            ws.write(r,0,row.get('item',row['key']),f['group']);ws.merge_range(r,1,r,6,row['discrimination'],f['group'])
            group_headers.append((r,row.get('group')))
        else:
            leaf_rows.append(n);groups.setdefault(row.get('group'),[]).append(n)
            for c,(field,value) in enumerate(zip(('item', 'description', 'unit'),
                    (row.get('item',row['key']), row['discrimination'], row.get('unit','')))):
                ws.write(r,c,value,f[f'{di_cell_tone(row, field)}_cell'])
            q=dec(v.get('quantity'));m=dec(v.get('material'));l=dec(v.get('labor'))
            ws.write_number(r,3,float(q),f['yellow_qty'])
            for c,key,num in [(4,'material',m),(5,'labor',l)]:
                target=targets.get((row['key'],key))
                fmt = f[f'{di_cell_tone(row, key)}_money']
                if target:_formula(ws,r,c,f"='DI Auxiliares'!G{target}",fmt,num)
                else:ws.write_number(r,c,float(num),fmt)
            for c,formula,cached in [(6,f'=E{n}+F{n}',m+l),(7,f'=ROUND(D{n}*G{n},2)',money(q*(m+l))),
                                     (8,f'=D{n}*E{n}',q*m),(9,f'=D{n}*F{n}',q*l)]:_formula(ws,r,c,formula,f['money'],cached)
        ws.set_row(r,30);r+=1
    for gr,group in group_headers:
        rr=groups.get(group,[])
        for c,letter in [(7,'H'),(8,'I'),(9,'J')]:
            vals=[row for row in data['di']['rows'] if row.get('row_type')=='ITEM' and row.get('group')==group]
            value=sum((money(dec(x['values'].get('quantity'))*(dec(x['values'].get('material'))+dec(x['values'].get('labor')))) if c==7 else dec(x['values'].get('quantity'))*dec(x['values'].get('material' if c==8 else 'labor')) for x in vals),ZERO)
            _formula(ws,gr,c,'='+_sumrefs(letter,rr),f['total'],value)
    ws.merge_range(r,0,r,6,'TOTAL DAS DESPESAS INDIRETAS',f['group'])
    raw=data['di'].get('calculation_totals',data['di']['totals'])
    for c,letter,key in [(7,'H','total'),(8,'I','material'),(9,'J','labor')]:
        val=data['di']['totals']['total'] if c==7 else raw[key]
        _formula(ws,r,c,'='+_sumrefs(letter,leaf_rows),f['total'],val)
    # Nomes explícitos permitem rastrear as bases sem hardcode de linha no BDI.
    wb.define_name('DI_Material',f"='DI'!$I${r+1}");wb.define_name('DI_MaoObra',f"='DI'!$J${r+1}")
    _setup(ws,9,r,a3=True)


def _write_bdi(wb,data,f,total_row):
    f = {**f, 'head': f['yellow_head'], 'group': f['white_cell'], 'total': f['white_total']}
    BDI_NON_TAX_KEYS = data["bdi_non_tax_keys"]
    BDI_TAX_KEYS = data["bdi_tax_keys"]
    ws=wb.add_worksheet('BDI')
    _columns(ws, f, [56, 24, 24, 80, 20, 20])
    _heading(ws, data, f, 'MEMÓRIA DE BDI', 5, 'yellow')
    ws.write_row(TABLE_HEADER_ROW,0,['ETAPA','VALOR / FATOR','BASE','FÓRMULA / OBSERVAÇÃO','MATERIAL + EQUIP.','MÃO DE OBRA'],f['head'])
    ws.set_row(TABLE_HEADER_ROW,32)
    b=data['bdi'];s=b['summary'];factor=dec(b.get('calculated_factor',1));configured=b.get('configured',False)
    rows={row['key']:23+i for i,row in enumerate(b['rows'])}
    non=_sumrefs('B',[rows[k] for k in BDI_NON_TAX_KEYS if k in rows]);tax=_sumrefs('B',[rows[k] for k in BDI_TAX_KEYS if k in rows])
    summary=[
        ('A - Custo direto',f"=Planilha!L{total_row}",s['direct_cost']['total'],'Soma dos custos das linhas principais'),
        ('B - Despesas indiretas','=DI_Material+DI_MaoObra',dec(data['di'].get('calculation_totals',data['di']['totals'])['material'])+dec(data['di'].get('calculation_totals',data['di']['totals'])['labor']),'Material + mão de obra sem arredondamento intermediário'),
        ('C - Subtotal de custo','=B11+B12',s['subtotal_cost']['total'],'A + B'),
        ('D - Lucro / administração e outros',f'=B13*({non})/100',s['non_tax_amount'],'C × soma dos percentuais não tributários'),
        ('F - Impostos',f'=IF(({tax})>=100,NA(),B14/(1-({tax})/100)-B14)',s['tax_amount'],'D / (1 - impostos) - D'),
        ('G - Venda da memória','=B13+B14+B15',s['total_sale'],'C + D + F'),
        ('Fator de venda', '=IF(B11>0,B16/B11,1)' if configured else '=1',factor,'G / A; fator 1 quando BDI não configurado'),
        ('BDI efetivo (%)','=(B17-1)*100',b['calculated_percentage'],'(fator - 1) × 100'),
        ('Venda final salva',f'=Planilha!F{total_row}',data['total'],'Inclui descontos e aplicação seletiva de BDI'),
        ('Fator real de venda','=IF(B11>0,B19/B11,1)',dec(data['total'])/dec(s['direct_cost']['total']) if dec(s['direct_cost']['total']) else 1,'Venda final / custo direto'),
    ]
    # Valores brutos para cache: não cachear apenas o resumo já arredondado.
    direct=sum((money(dec(i['quantity'])*dec(i['cost']['unit_cost'])) for i in items(data)),ZERO)
    di=data['di'].get('calculation_totals',data['di']['totals']);indirect=dec(di['material'])+dec(di['labor'])
    rates={row['key']:dec(row['values'].get('percentage')) for row in b['rows']}
    nr=sum((rates.get(k,ZERO) for k in BDI_NON_TAX_KEYS),ZERO)/100;tr=sum((rates.get(k,ZERO) for k in BDI_TAX_KEYS),ZERO)/100
    nt=(direct+indirect)*nr;tv=nt/(1-tr)-nt if tr<1 else ZERO
    cached=[direct,indirect,direct+indirect,nt,tv,direct+indirect+nt+tv,factor,dec(b['calculated_percentage']),dec(data['total']),dec(data['total'])/direct if direct else 1]
    for r,(label,formula,value,note) in enumerate(summary,10):
        tone = 'yellow' if r in (16,17,19) else 'green' if r == 18 else 'white'
        for c in range(6): ws.write_blank(r,c,None,f[f'{tone}_cell'])
        ws.write(r,0,label,f[f'{tone}_cell'])
        _formula(ws,r,1,formula,f[f'{tone}_factor' if r in (16,19) else f'{tone}_money'],cached[r-10])
        ws.write(r,3,note,f[f'{tone}_cell']);ws.set_row(r,30)
    mat=sum((money(dec(i['quantity'])*(dec(i['cost']['material'])+dec(i['cost']['equipment']))) for i in items(data)),ZERO)
    lab=sum((money(dec(i['quantity'])*dec(i['cost']['labor'])) for i in items(data)),ZERO)
    for r, fm, fl, cm, cl in [
        (10, f'=Planilha!K{total_row}+Planilha!M{total_row}', f'=Planilha!L{total_row}',mat,lab),
        (11, '=DI_Material','=DI_MaoObra',dec(di['material']),dec(di['labor'])),
        (12, '=E11+E12','=F11+F12',mat+dec(di['material']),lab+dec(di['labor']))]:
        _formula(ws,r,4,fm,f['money'],cm);_formula(ws,r,5,fl,f['money'],cl)
    ws.write_row(21,0,['DISCRIMINAÇÃO','PERCENTUAL (%)','VALOR (R$)','BASE'],f['head'])
    for idx,row in enumerate(b['rows'],22):
        tax = row['key'] in BDI_TAX_HIGHLIGHTS
        ws.write(idx,0,row['discrimination'],f['lime_cell'] if tax else f['cell'])
        ws.write_number(idx,1,float(dec(row['values'].get('percentage'))),f['lime_money'] if tax else f['bdi_input'])
        base='$B$13' if row['key']=='lucro' else '$B$14'
        raw=(direct+indirect if row['key']=='lucro' else nt)*dec(row['values'].get('percentage'))/100
        _formula(ws,idx,2,f'={base}*B{idx+1}/100',f['money'],raw);ws.write(idx,3,'C' if row['key']=='lucro' else 'D',f['cell']);ws.set_row(idx,30)
    end=22+len(b['rows']);ws.write(end,0,'TOTAL DEMONSTRATIVO',f['group'])
    _formula(ws,end,1,f'=SUM(B23:B{end})',f['total'],b.get('detail_total_percentage',0));_formula(ws,end,2,f'=SUM(C23:C{end})',f['total'],b.get('detail_total_amount',0))
    _setup(ws,5,end,header=TABLE_HEADER_ROW,a3=True)


def _write_components(wb,data,f,item_refs):
    ws=wb.add_worksheet('Composições');ws.write_row(TABLE_HEADER_ROW,0,['ITEM','COMPOSIÇÃO','COMPONENTE','UN.','ESTADO','COEFICIENTE EFETIVO','QTD. NA PLANILHA','MATERIAL UNIT.','M.O. UNIT.','EQUIP. UNIT.','CUSTO UNIT.','CUSTO TOTAL'],f['head'])
    _columns(ws, f, [14, 48, 48, 14, 14] + [18] * 7)
    _heading(ws, data, f, 'COMPOSIÇÕES E SUBCOMPOSIÇÕES', 11)
    ws.set_row(TABLE_HEADER_ROW,36)
    r=TABLE_HEADER_ROW + 1
    for item in items(data):
        for component in item['cost']['components']:
            n=r+1;v=component;q=dec(item['quantity'])*dec(v.get('coefficient'))
            state='Agrupador' if v.get('display_only') else 'Ativo' if v.get('enabled',True) else 'Desativado'
            desc=v.get('description_snapshot','');coef=dec(v.get('coefficient'));m=dec(v.get('material_unit_price'));l=dec(v.get('labor_unit_price'));e=dec(v.get('equipment_unit_price'))
            ws.write_row(r,0,[f"{item['number']}.{v.get('source_path',r)}",item['description'],desc,v.get('unit_snapshot',''),state],f['cell'])
            ws.write_number(r,5,float(coef),f['qty']);_formula(ws,r,6,f"=Planilha!D{item_refs[item['number']]}*F{n}",f['qty'],q)
            for c,num in [(7,m),(8,l),(9,e)]:ws.write_number(r,c,float(num),f['money'])
            _formula(ws,r,10,f'=SUM(H{n}:J{n})',f['money'],m+l+e)
            active=state=='Ativo'
            contribution = money(coef*m)+money(coef*l)+money(coef*e)
            # O backend arredonda material/M.O./equipamento por coeficiente antes de somar.
            formula = f'=IF(E{n}="Ativo",ROUND(Planilha!D{item_refs[item["number"]]}*(ROUND(F{n}*H{n},2)+ROUND(F{n}*I{n},2)+ROUND(F{n}*J{n},2)),2),0)'
            _formula(ws,r,11,formula,f['money'],money(dec(item['quantity'])*contribution) if active else 0)
            ws.set_row(r,max(30,14*ceil(max(len(desc),len(item['description']))/44)));r+=1
    _setup(ws,11,r,a3=True)


PDF_DOCUMENTS = ("PLANILHA", "BDI", "DI")


def validate_pdf_selection(audience, document):
    if audience not in ("CLIENT", "DARUIX"):
        raise ValueError("Use CLIENT ou DARUIX.")
    if document not in PDF_DOCUMENTS:
        raise ValueError("Use PLANILHA, BDI ou DI.")
    if audience == "CLIENT" and document != "PLANILHA":
        raise ValueError("A exportação do cliente contém somente a planilha de orçamento.")


def render_pdf(data, document="PLANILHA"):
    """Um relatório por arquivo, sempre em A4 paisagem, inclusive ao paginar."""
    validate_pdf_selection(data["audience"], document)
    report_title = {
        "PLANILHA": "PLANILHA ORÇAMENTÁRIA",
        "BDI": "MEMÓRIA DE BDI" if data["audience"] == "DARUIX" else "BDI - RESUMO",
        "DI": "DESPESAS INDIRETAS",
    }[document]
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import reportlab
    from pathlib import Path
    font_dir = Path(reportlab.__file__).parent / 'fonts'
    for name, filename in [('DaruixText', 'Vera.ttf'), ('DaruixBold', 'VeraBd.ttf')]:
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(font_dir / filename)))
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, PageBreak
    from reportlab.lib.utils import ImageReader
    out=BytesIO();page=landscape(A4);width=page[0]-64
    styles={
        'title':ParagraphStyle('title',fontName='DaruixBold',fontSize=15,leading=19,textColor=colors.HexColor('#C00D0E'),spaceAfter=10),
        'body':ParagraphStyle('body',fontName='DaruixText',fontSize=8,leading=11,spaceAfter=4),
        'cell':ParagraphStyle('cell',fontName='DaruixText',fontSize=7.5,leading=10),
        'num':ParagraphStyle('num',fontName='DaruixText',fontSize=7.5,leading=10,alignment=2),
        'head':ParagraphStyle('head',fontName='DaruixBold',fontSize=7.5,leading=10),
        'identity':ParagraphStyle('identity',fontName='DaruixText',fontSize=8,leading=11),
        'identity_red':ParagraphStyle('identity_red',fontName='DaruixBold',fontSize=8.5,leading=12,textColor=colors.HexColor(PALETTE['red'])),
        'band':ParagraphStyle('band',fontName='DaruixBold',fontSize=11,leading=14,alignment=1),
    }
    story=[]
    def p(text,style='cell'):return Paragraph(escape(str(text)).replace('\n','<br/>'),styles[style])
    tone = 'cyan' if document == 'DI' else 'yellow' if document == 'BDI' else 'gray'
    identity = []
    # Cabeçalho dividido em dois blocos equilibrados: logo à esquerda e dados à direita.
    header_logo_width = 165
    header_gap = 28
    header_side_padding = 16
    text_width = width - header_logo_width - header_gap - (header_side_padding * 2)
    for i, text in enumerate(heading_lines(data)):
        paragraph = p(text, 'identity_red' if i in (0, 6) else 'identity')
        _, height = paragraph.wrap(text_width - 16, page[1])
        identity.append((paragraph, height + 3))
    if document == 'PLANILHA' and data['audience'] == 'DARUIX':
        styles['identity_factor'] = ParagraphStyle('identity_factor', parent=styles['identity'],
                                                   fontName='DaruixBold', alignment=2)
        paragraph = p('Fator BDI: ' + br(data['bdi'].get('calculated_factor', 1), 6), 'identity_factor')
        _, height = paragraph.wrap(text_width - 16, page[1])
        identity.append((paragraph, height + 3))
    identity_height = sum(height for _, height in identity) + 12
    header_height = identity_height + 24
    # SimpleDocTemplate adds 6 pt of frame padding on either side.
    doc=SimpleDocTemplate(out,pagesize=page,rightMargin=26,leftMargin=26,
                          topMargin=26 + header_height + 10,bottomMargin=34,
                          title=f"{report_title} - Orçamento {data['number']}",author=COMPANY)
    def table(headers,rows,widths,numeric=(),groups=(),cell_tones=None,row_tones=None,red_cells=()):
        rendered=[[p(h,'head') for h in headers]]
        for r, row in enumerate(rows):
            rendered_row = []
            for c, value in enumerate(row):
                style = styles['num' if c in numeric else 'cell']
                if r in groups or (r,c) in red_cells:
                    style = ParagraphStyle(f'cell_{r}_{c}',parent=style,
                        fontName='DaruixBold' if r in groups else 'DaruixText',
                        textColor=colors.HexColor(PALETTE['red']) if (r,c) in red_cells else colors.black)
                if c in numeric or (c == 0 and str(value).replace('.', '').isdigit()):
                    # Mede também os totais em negrito. Reserva os 6 pt de padding
                    # de cada lado e reduz somente a fonte da célula que não cabe.
                    available = width * widths[c] - 13
                    measured = max((pdfmetrics.stringWidth(line, style.fontName, style.fontSize)
                                    for line in str(value).splitlines()), default=0)
                    font_size = style.fontSize * min(1, available / measured) if measured else style.fontSize
                    style = ParagraphStyle(f'number_{r}_{c}', parent=style,
                                           fontSize=font_size, splitLongWords=False)
                rendered_row.append(Paragraph(escape(str(value)).replace('\n','<br/>'),style))
            rendered.append(rendered_row)
        t=LongTable(rendered,colWidths=[width*x for x in widths],repeatRows=1,hAlign='LEFT',splitInRow=1)
        commands=[('BACKGROUND',(0,0),(-1,0),colors.HexColor(PALETTE[tone])),('GRID',(0,0),(-1,-1),.35,colors.HexColor('#C7C7C7')),
                  ('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]
        for row in groups:commands.append(('BACKGROUND',(0,row+1),(-1,row+1),colors.HexColor(PALETTE['green' if document == 'DI' else 'gray'])))
        for row, shade in (row_tones or {}).items():
            commands.append(('BACKGROUND',(0,row+1),(-1,row+1),colors.HexColor(PALETTE[shade])))
        for (row,col), shade in (cell_tones or {}).items():
            commands.append(('BACKGROUND',(col,row+1),(col,row+1),colors.HexColor(PALETTE[shade])))
        t.setStyle(TableStyle(commands));story.append(t);story.append(Spacer(1,12))
    def section(title,new_page=True,shade=None):
        if new_page:story.append(PageBreak())
        if shade:
            style=ParagraphStyle('section_band',parent=styles['head'],fontSize=10,leading=14,
                                 backColor=colors.HexColor(PALETTE[shade]),borderPadding=6,
                                 leftIndent=6,rightIndent=6,spaceAfter=12,keepWithNext=True)
            story.append(Paragraph(escape(title),style))
        else:
            story.append(p(title,'title'))
    if document == 'PLANILHA':
        internal = data['audience'] == 'DARUIX'
        rows=[];groups=[]
        def cost_values(item):
            c = item['cost']; q = dec(item['quantity'])
            return [br(c[key]) for key in ('material', 'labor', 'unit_cost')] + [
                br(money(q * dec(c[key]))) for key in ('material', 'labor', 'unit_cost')]
        for stage in data['stages']:
            groups.append(len(rows))
            stage_row = ['', f"Etapa {stage['number']} - {stage['name']} - Total da Etapa", '', '', '', br(stage['total'])]
            if internal:
                stage_row += ['', '', ''] + [br(sum((money(dec(i['quantity']) * dec(i['cost'][key]))
                                                  for i in stage['items']), ZERO))
                                              for key in ('material', 'labor', 'unit_cost')]
            rows.append(stage_row)
            for item in stage['items']:
                row = [item['number'], item['description'], item['unit'], br(item['quantity'],6).rstrip('0').rstrip(','), br(item['unit_price']), br(item['total'])]
                rows.append(row + cost_values(item) if internal else row)
                if internal:
                    for child in component_rows(item):
                        if child['group']:
                            groups.append(len(rows))
                        rows.append([child['number'], '  ' * child['depth'] + child['description'],
                                     child['unit'], br(child['quantity'],6).rstrip('0').rstrip(','), '', '']
                                    + cost_values(child))
        groups.append(len(rows))
        total_row = ['', 'TOTAL GERAL', '', '', '', br(data['total'])]
        if internal:
            total_row += ['', '', ''] + [br(sum((money(dec(i['quantity']) * dec(i['cost'][key]))
                                                for i in items(data)), ZERO))
                                          for key in ('material', 'labor', 'unit_cost')]
        rows.append(total_row)
        headers = ['Item','Discriminação','Un.','Qtd.' if internal else 'Quantidade','Unitário (R$)','Total (R$)']
        if internal:
            headers += ['Material unit.', 'M.O. unit.', 'Custo unit. total',
                        'Material total', 'M.O. total', 'Custo total']
            table(headers, rows, [.055,.245,.04,.06,.075,.075] + [.075]*6, range(3,12), groups)
            story.append(p('Unitário e total de venda são os salvos no Hub nas linhas principais. Componentes mostram custos; os totais das etapas não somam novamente os detalhes.', 'body'))
        else:
            table(headers, rows, [.06,.48,.05,.11,.14,.16], (3,4,5), groups)
    if document == 'BDI' and data['audience'] == 'DARUIX':
        b=data['bdi'];s=b['summary']
        table(['Custo','Material / equipamento','Mão de obra','Total'],
              [[label,br(s[key]['material']),br(s[key]['labor']),br(s[key]['total'])]
               for label,key in [('Direto','direct_cost'),('Indireto','indirect_cost'),('Subtotal','subtotal_cost')]],
              [.4,.2,.2,.2],(1,2,3))
        rows=[['A - Custo direto',br(s['direct_cost']['total']),'Soma dos custos diretos'],
              ['B - D.I.',br(s['indirect_cost']['total']),'Material + mão de obra, preservando a precisão interna'],
              ['C - Subtotal de custo',br(s['subtotal_cost']['total']),'A + B'],
              ['D - Lucro / administração e outros',br(s['non_tax_amount']),f"C × {br(s['non_tax_percentage'],4)}%"],
              ['E - Subtotal de venda',br(s['subtotal_sale']),'C + D'],
              ['F - Impostos',br(s['tax_amount']),f"D / (1 - {br(s['tax_percentage'],4)}%) - D"],
              ['G - Venda da memória',br(s['total_sale']),'E + F'],
              ['Fator BDI',br(b['calculated_factor'],12),'G / A'],
              ['BDI efetivo (%)',br(b['calculated_percentage'],4),'(fator - 1) × 100'],
              ['Venda final salva',br(data['total']),'Após descontos e aplicação seletiva do BDI']]
        table(['Etapa','Valor / fator','Cálculo'],rows,[.38,.20,.42],(1,),
              row_tones={7:'yellow',8:'yellow',9:'green'})
        bdi_tones = {}; red_cells = []
        for r, row in enumerate(b['rows']):
            if row['key'] in BDI_TAX_HIGHLIGHTS:
                bdi_tones[r,0] = bdi_tones[r,1] = 'lime'
            else:
                bdi_tones[r,1] = 'green'; red_cells.append((r,1))
        table(['Discriminação','Percentual (%)','Valor (R$)'],[[row['discrimination'],br(row['values'].get('percentage'),4),br(row['values'].get('amount'))] for row in b['rows']]+[['TOTAL DEMONSTRATIVO',br(b.get('detail_total_percentage'),4),br(b.get('detail_total_amount'))]],[.64,.18,.18],(1,2),groups=(len(b['rows']),),cell_tones=bdi_tones,red_cells=red_cells,row_tones={len(b['rows']):'white'})
    if document == 'DI' and data['audience'] == 'DARUIX':
        story.append(p('Unitário = material + mão de obra. Total da linha = ARRED(quantidade × unitário; 2). A base do BDI usa os produtos sem arredondamento intermediário.','body'))
        rows=[];groups=[];di_tones={}
        for row in data['di']['rows']:
            v=row['values']
            for col, field in enumerate(('item','description','unit','quantity','material','labor','total_unit','total')):
                di_tones[len(rows),col] = di_cell_tone(row,field)
            if row.get('row_type')=='GROUP':groups.append(len(rows))
            rows.append([row.get('item',row['key']),row['discrimination'],row.get('unit',''),br(v.get('quantity'),6),br(v.get('material'),4),br(v.get('labor'),4),br(v.get('unit_price'),4),br(v.get('total'))])
        rows.append(['','TOTAL D.I.','','','','','',br(data['di']['totals']['total'])]);groups.append(len(rows)-1)
        table(['Item','Discriminação','Un.','Quantidade','Material','Mão de obra','Unitário','Total'],rows,[.065,.365,.05,.10,.105,.105,.105,.105],range(3,8),groups,cell_tones=di_tones)
        d=data['di'];raw=d.get('calculation_totals',d['totals'])
        story.append(p(f"Total D.I. por linhas: R$ {br(d['totals']['total'])}. Base sem arredondamento: material {br(raw['material'],10)} + mão de obra {br(raw['labor'],10)}.",'body'))
        for aux in d.get('auxiliary_tables',[]):
            section('D.I. - '+str(aux.get('title') or aux.get('discrimination') or aux['key']),shade='pink')
            story.append(p('Transporte: quantidade × tarifa × pessoas × passagens × período; demais itens: quantidade × fator × unitário. Cada linha é arredondada em centavos.','body'))
            rows=[[row.get('discrimination') or row.get('label') or row['key'],br(row['values'].get('quantity'),6),br(row['values'].get('factor',1),4),br(row['values'].get('unit_price'),4),br(row['values'].get('total'))] for row in aux['rows']]
            rows.append(['TOTAL','','','',br(aux.get('total'))])
            aux_tones = {(r,c): 'yellow' if c in (1,2) else 'cyan' for r in range(len(rows)-1) for c in (1,2,3)}
            table(['Discriminação','Quantidade','Fator','Unitário','Total'],rows,[.48,.13,.13,.13,.13],(1,2,3,4),groups=(len(rows)-1,),cell_tones=aux_tones)
    def footer(canvas,doc):
        canvas.saveState()
        top = page[1] - 26
        canvas.setFillColor(colors.HexColor(PALETTE[tone] if document in ('DI','BDI') else PALETTE['white']))
        canvas.rect(32,top-identity_height,width,identity_height,fill=1,stroke=0)
        logo = ImageReader(str(MAIN_LOGO_PATH)); iw, ih = logo.getSize()
        logo_width = header_logo_width
        logo_height = logo_width * ih / iw
        logo_x = 32 + header_side_padding
        logo_y = top - identity_height + (identity_height - logo_height) / 2
        canvas.drawImage(logo,logo_x,logo_y,
                         width=logo_width,height=logo_height,mask='auto')
        # Centraliza verticalmente o bloco de informações no mesmo cabeçalho do logo.
        identity_total_height = sum(height for _, height in identity)
        y = top - (identity_height - identity_total_height) / 2
        text_x = logo_x + header_logo_width + header_gap
        for paragraph, height in identity:
            paragraph.drawOn(canvas,text_x,y-height+3)
            y -= height
        canvas.setFillColor(colors.HexColor(PALETTE[tone]))
        canvas.rect(32,top-header_height,width,24,fill=1,stroke=0)
        canvas.setStrokeColor(colors.HexColor('#808080'));canvas.setLineWidth(.5)
        canvas.line(32,top-header_height,page[0]-32,top-header_height)
        title_paragraph = p(report_title,'band');title_paragraph.wrap(width,24)
        title_paragraph.drawOn(canvas,32,top-header_height+5)
        # Rodapé baixo: o logo Hub fica totalmente contido e nunca invade a tabela.
        footer_logo = ImageReader(str(HUB_FOOTER_SMALL_PATH)); fiw, fih = footer_logo.getSize()
        footer_logo_width = 32
        footer_logo_height = footer_logo_width * fih / fiw
        footer_y = 9
        canvas.drawImage(footer_logo,32,footer_y,width=footer_logo_width,height=footer_logo_height,mask='auto')
        canvas.setFillColor(colors.black);canvas.setFont('DaruixText',7)
        baseline = 15
        canvas.drawString(72,baseline,'R.S. DARUIX ENGENHARIA LTDA. - '+('Uso interno - ' if data['audience']=='DARUIX' else '')+report_title)
        canvas.drawRightString(page[0]-32,baseline,f'Página {doc.page}');canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()


def pdf_filename_prefix(data):
    import re
    pc = re.sub(r"[^A-Za-z0-9_.-]+", "-", data.get("proposal_code") or "ORCAMENTO").strip(".") or "ORCAMENTO"
    audience = "CLIENTE" if data["audience"] == "CLIENT" else "DARUIX"
    return f"{pc}-R{data['revision']:02d}-{audience}"


def render_pdf_bundle(data):
    """Cliente: somente Planilha; Daruix: Planilha, BDI e DI do mesmo snapshot."""
    from zipfile import ZipFile, ZIP_DEFLATED
    out = BytesIO()
    prefix = pdf_filename_prefix(data)
    validate_pdf_selection(data['audience'], 'PLANILHA')
    documents = ('PLANILHA',) if data['audience'] == 'CLIENT' else PDF_DOCUMENTS
    with ZipFile(out, "w", compression=ZIP_DEFLATED) as archive:
        for document in documents:
            archive.writestr(f"{prefix}-{document}.pdf", render_pdf(data, document))
    return out.getvalue()
