"""Leitura assistida de NF-e em XML ou fotografia.

O resultado é uma sugestão para conferência humana; não valida situação fiscal.
"""
import os
import re
from decimal import Decimal, InvalidOperation

from defusedxml import ElementTree as ET

NS = {'n': 'http://www.portalfiscal.inf.br/nfe'}


def _value(parent, path):
    return (parent.findtext(path, default='', namespaces=NS) if parent is not None else '').strip()


def _find(pattern, text, flags=re.IGNORECASE):
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else ''


def _clean_line(line):
    return re.sub(r'\s+', ' ', line).strip(' :-\t')


def _field(lines, pattern):
    for line in lines:
        match = re.search(pattern, line, re.IGNORECASE)
        if match:
            return _clean_line(match.group(1))
    return ''


def _money(raw):
    if not raw:
        return None
    clean = re.sub(r'[^\d,.]', '', raw)
    if not clean:
        return None
    if ',' in clean:
        clean = clean.replace('.', '').replace(',', '.')
    try:
        return str(Decimal(clean).quantize(Decimal('0.01')))
    except InvalidOperation:
        return None


def _read_image(upload):
    from PIL import Image, ImageEnhance, ImageOps
    import pytesseract

    tesseract_cmd = os.getenv('TESSERACT_CMD', '').strip()
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    image = Image.open(upload)
    image.verify()
    upload.seek(0)
    image = Image.open(upload)
    if image.width * image.height > 25_000_000:
        raise ValueError('Imagem muito grande (limite: 25 megapixels).')
    image = ImageOps.exif_transpose(image).convert('RGB')
    image = ImageEnhance.Contrast(ImageOps.grayscale(image)).enhance(1.5)
    try:
        text = pytesseract.image_to_string(image, lang='por+eng', config='--psm 3')
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError('Executável Tesseract não encontrado no servidor.') from exc
    except pytesseract.TesseractError as exc:
        raise RuntimeError('O Tesseract não conseguiu processar a imagem.') from exc

    return _parse_ocr_text(text)


def _parse_ocr_text(text):
    lines = [_clean_line(x) for x in text.splitlines() if x.strip()]
    # Evita confundir o CNPJ do fornecedor com o CNPJ do cliente.
    start = next((i + 1 for i, ln in enumerate(lines) if re.search(r'EMITENTE|FORNECEDOR', ln, re.I)), 0)
    end = next((i for i in range(start, len(lines)) if re.search(r'DESTINAT[ÁA]RIO|CLIENTE', lines[i], re.I)), len(lines))
    issuer_lines = lines[start:end]
    if not issuer_lines:
        issuer_lines = lines

    number = _field(lines, r'(?:N[ÚU]MERO(?:\s+DA\s+(?:NF|NOTA))?|N[º°]\s*NF|NF[-eE]?\s*(?:N[º°.]|N\.))\s*[:#.-]?\s*(\d{1,12})\b')
    series = _field(lines, r'\bS[ÉE]RIE\s*[:#.-]?\s*(\d{1,4})\b')
    issuer_name = _field(issuer_lines, r'RAZ[ÃA]O\s+SOCIAL\s*[:\-]?\s*(.+)$')
    trade_name = _field(issuer_lines, r'NOME\s+FANTASIA\s*[:\-]?\s*(.+)$')
    # OCR pode ler CNPJ como CNP) ou CNPJ; buscamos o número na seção do emitente.
    cnpj = _field(issuer_lines, r'\b(?:CNPJ|CNP\W)\s*[:\-]?\s*(\d{2}[.\s]?\d{3}[.\s]?\d{3}[/\s]?\d{4}[-\s]?\d{2})')
    if not cnpj:
        cnpj = _field(issuer_lines, r'\b(\d{2}[.\s]?\d{3}[.\s]?\d{3}[/\s]?\d{4}[-\s]?\d{2})\b')
    # Tolerância a pequenas falhas na palavra TOTAL, como TOTA~.
    amount = _field(lines, r'\bVALOR\s+TOTA\S*\s+(?:DA\s+NOTA|DA\s+NF|NF)?\s*[:\-]?\s*(?:R\$\s*)?([\d.]+,\d{2})\b')
    if not amount:
        amount = _field(lines, r'\b(?:TOTAL\s+A\s+PAGAR|VALOR\s+A\s+PAGAR)\s*[:\-]?\s*(?:R\$\s*)?([\d.]+,\d{2})\b')
    if not amount:
        for pos, line in enumerate(lines[:-1]):
            if re.search(r'VALOR\s+TOTA\S*\s+(?:DA\s+NOTA|DA\s+NF|NF)', line, re.I):
                amount = _find(r'(?:R\$\s*)?([\d.]+,\d{2})', lines[pos + 1])
                if amount:
                    break

    result = {
        'number': number,
        'series': series,
        'issuer_name': issuer_name,
        'trade_name': trade_name,
        'issuer_document': re.sub(r'\D', '', cnpj),
        'total_value': _money(amount),
        'access_key': '',
        'description': '',
        'source': 'OCR',
        'warnings': ['Leitura automática: confira os dados antes de salvar.'],
        'raw_text': text[:12000],
    }
    for field, label in [('number', 'número'), ('issuer_name', 'razão social'), ('issuer_document', 'CNPJ'), ('total_value', 'valor total')]:
        if not result[field]:
            result['warnings'].append(f'Não foi possível identificar {label}; preencha manualmente.')
    return result


def read_invoice(upload):
    name = upload.name.lower()
    if name.endswith('.xml'):
        root = ET.parse(upload).getroot()
        inf = root if root.tag == f'{{{NS["n"]}}}infNFe' else root.find('.//n:infNFe', NS)
        if inf is None:
            raise ValueError('XML sem infNFe.')
        ide, emit = inf.find('n:ide', NS), inf.find('n:emit', NS)
        if ide is None or emit is None:
            raise ValueError('NF-e incompleta.')
        return {
            'number': _value(ide, 'n:nNF'),
            'series': _value(ide, 'n:serie'),
            'issuer_name': _value(emit, 'n:xNome'),
            'trade_name': _value(emit, 'n:xFant'),
            'issuer_document': _value(emit, 'n:CNPJ') or _value(emit, 'n:CPF'),
            'total_value': _value(inf, 'n:total/n:ICMSTot/n:vNF') or None,
            'access_key': inf.attrib.get('Id', '').removeprefix('NFe'),
            'source': 'XML', 'description': '',
            'warnings': ['Confira a autorização e situação fiscal da nota.'],
        }
    if name.endswith('.pdf'):
        return _read_pdf(upload)
    if not name.endswith(('.png', '.jpg', '.jpeg', '.webp')):
        raise ValueError('Formato não suportado. Envie XML, PDF, JPG, PNG ou WEBP.')
    return _read_image(upload)


def _parse_fiscal_pdf_layout(text):
    """Layouts conhecidos de DANFE e NFS-e; não consulta nem valida SEFAZ."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    upper = text.upper()
    cnpj_re = r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"
    money_re = r"\d{1,3}(?:\.\d{3})*,\d{2}"

    result = {
        'number': '', 'series': '', 'issuer_name': '', 'trade_name': '',
        'issuer_document': '', 'total_value': None, 'access_key': '',
        'description': '', 'source': 'OCR',
        'warnings': ['Dados extraídos do PDF; confira antes de salvar.'],
        'raw_text': text[:12000],
    }
    if 'DADOS DO PRESTADOR DE SERVIÇO' in upper and ('NFS-E' in upper or 'NOTA FISCAL DE SERVIÇO' in upper):
        result['number'] = _find(r'N[ÚU]MERO DA NOTA FISCAL\s*\n\s*(\d{1,12})\b', text)
        section = re.search(r'Dados do Prestador de Serviço(.*?)Identifica(?:ç|c)[ãa]o da Nota Fiscal', text, re.I | re.S)
        if section:
            prestador = [v.strip() for v in section.group(1).splitlines() if v.strip()]
            # Nome e fantasia vêm no início do quadro do prestador, antes de endereço/contato.
            names = []
            for ln in prestador:
                name = re.split(r'\s{3,}', ln)[0].strip()
                if re.search(r'Data de|Competência|Cód\.|Autenticidade|Inscrição|CPF/CNPJ|Fone|CEP|@|\d{2}[./-]\d', name, re.I):
                    continue
                if not re.match(r'^[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 &.\-]+$', name):
                    continue
                names.append(name)
                if len(names) == 2:
                    break
            if names:
                result['issuer_name'] = names[0]
            if len(names) > 1:
                result['trade_name'] = names[1]
            match = re.search(cnpj_re, section.group(1))
            if match:
                result['issuer_document'] = re.sub(r'\D', '', match.group())
        # Em algumas NFS-e não existe campo de série; não inventar uma.
        amount_section = re.search(r'Vl\.\s*Total dos Serviços(.*?)(?:Construção Civil|Informações Adicionais)', text, re.I | re.S)
        if amount_section:
            amounts = re.findall(r'R\$\s*('+money_re+r')', amount_section.group(1))
            if amounts:
                result['total_value'] = _money(amounts[0])
        key = _find(r'Chave de acesso no Ambiente de Dados Nacional:\s*(\d{44,50})', text)
        result['access_key'] = key
        if not result['number']:
            result['warnings'].append('Número da NFS-e não identificado.')
        return result

    if 'DANFE' in upper and 'CHAVE DE ACESSO' in upper:
        result['number'] = _find(r'\bN[º°o]\s*(\d{1,9})', text)
        result['series'] = _find(r'\bS[ÉE]RIE\s*:\s*(\d{1,4})', text)
        result['access_key'] = _find(r'\bNFe(\d{44})\b', text)
        # Logo antes do DANFE fica o nome fantasia (pode não haver razão social impressa).
        header = re.search(r'RECEBEMOS DE\s+(.+?)\s+OS PRODUTOS', text, re.I)
        if header:
            result['issuer_name'] = header.group(1).strip()
        # Layout: CNPJ/CPF da seção do emitente ocorre ANTES de DESTINATÁRIO.
        emitter_text = re.split(r'\bDESTINAT[ÁA]RIO\b', text, maxsplit=1, flags=re.I)[0]
        cnpjs = re.findall(cnpj_re, emitter_text)
        if cnpjs:
            result['issuer_document'] = re.sub(r'\D', '', cnpjs[-1])
        # Campo final, não confundir com valor total dos produtos.
        amount_section = re.search(r'VALOR TOTAL DA NOTA\s*\n([^\n]+)', text, re.I)
        if amount_section:
            amounts = re.findall(money_re, amount_section.group(1))
            if amounts:
                result['total_value'] = _money(amounts[-1])
        if not result['total_value']:
            header_amounts = re.search(r'VALOR DO FRETE.*?VALOR TOTAL DA NOTA\s*\n([^\n]+)', text, re.I | re.S)
            if header_amounts:
                amounts = re.findall(money_re, header_amounts.group(1))
                if amounts:
                    result['total_value'] = _money(amounts[-1])
        result['warnings'].append('DANFE: o nome do emitente pode ser nome fantasia; confira a razão social.')
        return result
    return None


def _read_pdf(upload):
    """Extract text from a PDF, falling back to OCR for scanned pages.

    Limits are intentional: PDF rendering can consume significant resources.
    """
    import io
    from pypdf import PdfReader

    try:
        pdf_bytes = upload.read()
        if len(pdf_bytes) > 10 * 1024 * 1024:
            raise ValueError('PDF excede o limite de 10 MB.')
        document = PdfReader(io.BytesIO(pdf_bytes), strict=False)
        if document.is_encrypted:
            raise ValueError('PDF protegido por senha não é suportado.')
        if not 1 <= len(document.pages) <= 5:
            raise ValueError('PDF deve conter entre 1 e 5 páginas.')
        page_texts = [(page.extract_text(extraction_mode='layout') or '') for page in document.pages]
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('Não foi possível abrir o PDF. Verifique se o arquivo é válido.') from exc

    text = '\n'.join(page_texts)
    specialized = _parse_fiscal_pdf_layout(text)
    if specialized and specialized.get('number') and specialized.get('issuer_document'):
        return specialized
    result = _parse_ocr_text(text)
    result['warnings'].insert(0, 'Dados extraídos do PDF; confira antes de salvar.')

    # PDFs may have a text layer with headers, but not all actual field values.
    required = ('number', 'issuer_name', 'issuer_document', 'total_value')
    if sum(bool(result.get(field)) for field in required) >= 3:
        return result

    try:
        import pypdfium2 as pdfium
        import pytesseract
        from PIL import ImageOps, ImageEnhance
        cmd = os.getenv('TESSERACT_CMD', '').strip()
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd
        pdf = pdfium.PdfDocument(pdf_bytes)
        ocr_text = []
        for index in range(len(pdf)):
            page = pdf[index]
            bitmap = page.render(scale=2)  # ~144 DPI
            image = bitmap.to_pil().convert('RGB')
            if image.width * image.height > 25_000_000:
                raise ValueError('Página de PDF muito grande para leitura.')
            image = ImageEnhance.Contrast(ImageOps.grayscale(image)).enhance(1.5)
            ocr_text.append(pytesseract.image_to_string(image, lang='por+eng', config='--psm 3'))
            page.close()
        pdf.close()
        ocr_result = _parse_ocr_text('\n'.join(ocr_text))
        for key in ('number','series','issuer_name','trade_name','issuer_document','total_value'):
            if not result.get(key) and ocr_result.get(key):
                result[key] = ocr_result[key]
        result['raw_text'] = ('\n'.join(ocr_text))[:12000]
        result['warnings'] = ['Leitura de PDF com OCR: confira os dados antes de salvar.']
        for key, label in [('number','número'),('issuer_name','razão social'),('issuer_document','CNPJ'),('total_value','valor total')]:
            if not result.get(key):
                result['warnings'].append(f'Não foi possível identificar {label}; preencha manualmente.')
        return result
    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError('Não foi possível executar o OCR do PDF.') from exc

# DANFE digitalizado: o OCR frequentemente quebra os rótulos de uma tabela,
# mas preserva números, CNPJ e nomes em linhas próximas do cabeçalho.
_original_parse_ocr_text = _parse_ocr_text


def _parse_ocr_text(text):
    """Complementa o parser genérico sem assumir campos não reconhecidos."""
    result = _original_parse_ocr_text(text)
    header = re.split(r'DESTINAT[ÁA]RIO\s*[/\\-]?\s*REMETENTE', text, maxsplit=1, flags=re.I)[0]
    # NF-e Nº 000.050.264 / N° 000,050.264, inclusive sem espaço no OCR.
    if not result['number']:
        m = re.search(r'\bN\s*[º°o.]\s*([0-9]{1,3}(?:[.,\s][0-9]{3}){1,2})', header, re.I)
        if m:
            result['number'] = re.sub(r'\D', '', m.group(1))
    if not result['series']:
        m = re.search(r'S[ÉE]RIE\s*[:.]?\s*0*([0-9]{1,3})', header, re.I)
        if m:
            result['series'] = m.group(1).zfill(3)
    # O nome do emitente geralmente é impresso ao lado do logotipo do DANFE.
    if not result['issuer_name']:
        match = re.search(r'(?im)^\s*((?:[A-ZÀ-Ý][A-ZÀ-Ý\s.&-]{4,})\s+(?:LTDA|S/?A|EIRELI|ME))\s*(?:\||$)', header)
        if not match:
            match = re.search(r'REC[EI][A-Z ]*\s+DE\s+(.{5,100}?)\s+(?:OS\s+PRODUTOS|EMISS[ÃA]O|NF-e)', header, re.I)
        if match:
            name = re.sub(r'\s+', ' ', match.group(1)).strip(' |-.')
            if len(name) <= 100:
                result['issuer_name'] = name
    # Segunda passagem pelo nome em caixa alta, sem engolir o texto do recibo.
    candidates = re.findall(r'(?m)^\s*([A-ZÀ-Ý][A-ZÀ-Ý &.]{5,90}\s+LTDA)\b', header)
    if candidates:
        result['issuer_name'] = min((re.sub(r'\s+', ' ', c).strip() for c in candidates), key=len)
    # Sempre restrito ao cabeçalho do emitente, nunca à inscrição estadual.
    if not result['issuer_document'] or not re.search(r'\d{14}', result['issuer_document']):
        result['issuer_document'] = ''
    cnpj_match = re.search(r'(?<!\d)(\d{2}\s*[.]\s*\d{3}\s*[.]\s*\d{3}\s*[/]\s*\d{4}\s*[-]\s*\d{2})(?!\d)', header)
    if cnpj_match:
        result['issuer_document'] = re.sub(r'\D', '', cnpj_match.group(1))
    # Último valor monetário da linha abaixo de VALOR TOTAL DA NOTA.
    if result['total_value'] is None:
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if re.search(r'VALOR\s+TOTAL\s*DA\s+NOTA', line, re.I):
                for candidate in (line, *(lines[i + 1:i + 3])):
                    numbers = re.findall(r'\b\d{1,3}(?:\.\d{3})*,\d{2}\b', candidate)
                    if numbers:
                        result['total_value'] = _money(numbers[-1])
                        break
                if result['total_value'] is not None:
                    break
    if result['total_value'] is None:
        # No DANFE impresso existe também "VALOR TOTAL R$ ..." no recibo.
        match = re.search(r'VALOR\s+TOTAL\s*R\$\s*([0-9.,]+)', header, re.I)
        if match:
            result['total_value'] = _money(match.group(1))
    # Remove alertas de campos que acabaram de ser recuperados.
    labels = {'number': 'número', 'issuer_name': 'razão social',
              'issuer_document': 'CNPJ', 'total_value': 'valor total'}
    result['warnings'] = [w for w in result['warnings'] if not any(
        result[k] and f'Não foi possível identificar {label}' in w
        for k, label in labels.items()
    )]
    return result

_original_read_image = _read_image


def _read_image(upload):
    """Segunda estratégia de OCR para fotografias com texto pequeno."""
    first = _original_read_image(upload)
    if all(first.get(key) for key in ('number', 'series', 'issuer_name', 'issuer_document', 'total_value')):
        return first
    from PIL import Image, ImageOps
    import pytesseract
    upload.seek(0)
    image = ImageOps.exif_transpose(Image.open(upload))
    if image.width * image.height > 25_000_000:
        raise ValueError('Imagem muito grande (limite: 25 megapixels).')
    grayscale = ImageOps.autocontrast(ImageOps.grayscale(image))
    scale = min(2.0, max(1.0, 2200 / max(image.size)))
    if scale > 1:
        grayscale = grayscale.resize((round(grayscale.width * scale), round(grayscale.height * scale)))
    text = pytesseract.image_to_string(grayscale, lang='por+eng', config='--psm 6')
    second = _parse_ocr_text(text)
    for key in ('number', 'series', 'issuer_name', 'issuer_document', 'total_value', 'access_key'):
        if not first.get(key) and second.get(key):
            first[key] = second[key]
    first['raw_text'] = (first.get('raw_text', '') + '\n--- OCR alternativo ---\n' + text)[:12000]
    labels = {'number': 'número', 'issuer_name': 'razão social',
              'issuer_document': 'CNPJ', 'total_value': 'valor total'}
    first['warnings'] = [w for w in first['warnings'] if not any(
        first[k] and f'Não foi possível identificar {label}' in w
        for k, label in labels.items()
    )]
    return first


# NFS-e Nacional (DANFSe): prestador e tomador são entidades diferentes.
def _parse_nfse_nacional(text):
    if not re.search(r'NFS[\s-]*[eE]|DANFS', text, re.I) or not re.search(r'EMITENTE\s+DA\s+NFS|PRESTADOR\s+DO\s+SERVI', text, re.I):
        return None
    lines = [_clean_line(x) for x in text.splitlines() if x.strip()]
    upper = text.upper()
    start = re.search(r'EMITENTE\s+DA\s+NFS', text, re.I)
    end = re.search(r'TOMADOR\s+DO\s+SERVI', text, re.I)
    provider = text[start.start():end.start()] if start and end and end.start() > start.start() else ''
    result = {
        'number': '', 'series': '', 'issuer_name': '', 'trade_name': '',
        'issuer_document': '', 'total_value': None, 'access_key': '',
        'description': '', 'source': 'OCR', 'raw_text': text[:12000],
        'warnings': ['NFS-e: confira os campos reconhecidos antes de salvar.'],
    }
    number = re.search(r'N[úu]mero\s+da\s+NFS\s*[-eE]*\s*[:\s]*([0-9]{1,12})', text, re.I)
    if number:
        result['number'] = number.group(1)
    # Nacional não apresenta série fiscal equivalente à NF-e de produtos.
    name = re.search(r'(?im)^\s*(?:\[)?([A-ZÀ-Ý][A-ZÀ-Ý\s]{7,100})\s*$', provider)
    if name:
        candidate = name.group(1).strip()
        if not re.search(r'EMITENTE|PRESTADOR|NOME|ENDERE|SIM[P]?LES|REGIME|MUNIC[IÍ]PIO|CNPJ|CPF', candidate):
            result['issuer_name'] = candidate.split(' fola')[0].split(' Nola')[0].strip()
    if not result['issuer_name']:
        m = re.search(r'(?im)^(?:\[)?([A-ZÀ-Ý]+(?:\s+[A-ZÀ-Ý]+){2,8})\s*(?:[|\']|$)', provider)
        if m:
            result['issuer_name'] = m.group(1).split(' fola')[0].split(' Nola')[0].strip()
    # Reconhece CPF/CNPJ APENAS no bloco do emitente.
    doc = re.search(r'(?<!\d)(\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}|\d{2}[.\s]?\d{3}[.\s]?\d{3}[/\s]?\d{4}[-\s]?\d{2})(?!\d)', provider)
    if doc:
        result['issuer_document'] = re.sub(r'\D', '', doc.group(1))
    # Primeiro valor no quadro VALOR TOTAL DA NFS-e; não usar valores dos tributos.
    amount = re.search(r'VALOR\s+L[IÍ]QUIDO\s+DA\s+NFS\s*[.\-eE]*\s*(?:R\$\s*)?([0-9][\d.,]*)', text, re.I)
    if not amount:
        amount = re.search(r'VALOR\s+DO\s+SERVI[CÇ]O\s*(?:R\$\s*)?([\d.,]+)', text, re.I)
    if not amount:
        amount = re.search(r'VALOR\s+L[IÍ]QUIDO\s+DA\s+NFS[^\n]*\n\s*R\$\s*([\d.,]+)', text, re.I)
    if amount:
        result['total_value'] = _money(amount.group(1))
    for key, label in [('number','número'), ('issuer_name','nome do prestador'), ('issuer_document','CPF/CNPJ do prestador'), ('total_value','valor')]:
        if not result[key]:
            result['warnings'].append('Não foi possível reconhecer ' + label + '; confira manualmente.')
    return result


_previous_parse_ocr_text = _parse_ocr_text

def _parse_ocr_text(text):
    special = _parse_nfse_nacional(text)
    return special if special is not None else _previous_parse_ocr_text(text)


_previous_read_image = _read_image

def _read_image(upload):
    # Para DANFSe, recortes evitam que tabelas e carimbos confundam o OCR.
    from PIL import Image, ImageOps, ImageEnhance
    import pytesseract
    upload.seek(0)
    img = ImageOps.exif_transpose(Image.open(upload)).convert('RGB')
    if img.width * img.height > 25_000_000:
        raise ValueError('Imagem muito grande (limite: 25 megapixels).')
    gray = ImageOps.autocontrast(ImageOps.grayscale(img))
    # Identificação do tipo por cabeçalho, tolerante a DANFSe / NFSe.
    head = gray.crop((0, 0, img.width, int(img.height * .27)))
    head = head.resize((head.width * 2, head.height * 2))
    header_text = pytesseract.image_to_string(head, lang='por+eng', config='--psm 6')
    if re.search(r'NFS\s*[-]?[eE]|DANFS', header_text, re.I):
        # Três áreas: cabeçalho/número, emitente e total de serviços.
        parts = [
            gray.crop((0, 0, img.width, int(img.height * .24))),
            gray.crop((0, int(img.height * .14), img.width, int(img.height * .42))),
            gray.crop((0, int(img.height * .47), img.width, int(img.height * .83))),
        ]
        texts = [pytesseract.image_to_string(x.resize((x.width * 2, x.height * 2)), lang='por+eng', config='--psm 6') for x in parts]
        # Região inferior com valor líquido frequentemente é perdida no OCR da página inteira.
        value_crop = gray.crop((int(img.width * .58), int(img.height * .61), img.width, int(img.height * .78)))
        value_text = pytesseract.image_to_string(value_crop.resize((value_crop.width * 3, value_crop.height * 3)), lang='por+eng', config='--psm 6')
        combined = '\n'.join(texts + [value_text])
        result = _parse_nfse_nacional(combined)
        if result is not None:
            return result
    upload.seek(0)
    return _previous_read_image(upload)


# NFS-e municipal (Sorocaba e variações do padrão com campos em colunas).
# Mantido separado do DANFE de produtos e da NFS-e nacional.
def _parse_nfse_municipal(text):
    if not re.search(r'N[ÚU]MERO\s*/\s*S[ÉE]RIE|NUMERO\s*/\s*SERIE|VALOR\s+TOTAL\s+DA\s+NOTA', text, re.I):
        return None
    if not re.search(r'NFS\s*[-–]?\s*[eE]|NOTA\s+FISCAL\s+DE\s+SERVI', text, re.I):
        return None
    if not re.search(r'EMITENTE\s+DA\s+NFS\s*[-–]?[eEoO]?|TOMADOR\s+DO\s+SERVI', text, re.I):
        return None
    lines = [_clean_line(s) for s in text.splitlines() if s.strip()]
    top = text.split('TOMADOR DO SERVI', 1)[0]
    issuer_match = re.search(r'EMITENTE\s+DA\s+NFS\s*[-–]?[eEoO]?', top, re.I)
    issuer = top[issuer_match.end():] if issuer_match else ''
    # Alguns OCRs repetem o cabeçalho do emitente. Não usar rótulos/e-mail como nome.
    name = ''
    matches = list(re.finditer(r'NOME\s*/\s*RAZ[ÃA]O\s+SOCIAL|NOME\s+EMPRESARIAL', issuer, re.I))
    for m in matches:
        tail = issuer[m.end():]
        for line in tail.splitlines():
            candidate = _clean_line(line)
            candidate = re.split(r'\s+(?:E-?MAIL|ENDERE[CÇ]O|INSCRI[CÇ][ÃA]O)\b', candidate, maxsplit=1, flags=re.I)[0].strip()
            if (len(candidate) >= 8 and not re.search(r'@|\b(?:E-?MAIL|CPF|CNPJ|ENDERE|NOME|INSCRI|MUNIC[IÍ]PIO|FINANCEIRO|\.COM|\bHTTP)\b', candidate, re.I)
                    and re.search(r'[A-Za-zÀ-ÿ]{3}', candidate)):
                name = candidate
                break
        if name:
            break
    doc = re.search(r'(?<!\d)(\d{2}[.,]\d{3}[.,]\d{3}[/\s]\d{4}[-\s]\d{2}|\d{3}[.,]\d{3}[.,]\d{3}[-\s]\d{2})(?!\d)', issuer)
    number = ''
    series = ''
    # Campo da NFS-e de Sorocaba: "Número / Série" seguido de "3737 / U".
    # Também aparece na mesma linha que data/competência em OCR de tabelas.
    head = top[:issuer_match.start()] if issuer_match else top[:1200]
    tokens = re.findall(r'(?<!\w)(\d{3,8})\s*/\s*([A-Z0-9]{1,3})(?!\w)', head, re.I)
    for n, sr in tokens:
        if not re.match(r'(?:19|20)\d{2}$', n) and not (len(n) == 6 and len(sr) == 2):
            number, series = n, sr.upper()
            break
    if not number:
        m = re.search(r'(?:N[ÚU]MERO\s*/\s*S[ÉE]RIE|N[ÚU]MERO\s+DA\s+NFS)[^\n]*\n[^\n]*?\b(\d{2,8})\s*[/|]\s*([A-Za-z0-9]{1,3})\b', head, re.I)
        if m:
            number, series = m.group(1), m.group(2).upper()
    if not number:
        # 'a7371U' OCR produz uma string sem separador; não deduzir número
        # se faltarem evidências suficientes.
        pass
    amount = None
    # Valor líquido, não valor de serviço bruto nem base de ISSQN.
    m = re.search(r'VALOR\s+L[ÍI]QUIDO\s*[:\-]?\s*(?:R\$\s*)?(\d{1,3}(?:\.\d{3})+,\d{2})', text, re.I)
    if m:
        amount = _money(m.group(1))
    if amount is None:
        # Tabela "VALOR TOTAL DA NOTA" com rótulos em uma linha e valores na próxima.
        m = re.search(r'VALOR\s+TOTAL\s+DA\s+NOTA(?P<section>.*?)(?:INFORMA[CÇ][ÕO]ES\s+COMPLEMENTARES|$)', text, re.I | re.S)
        if m:
            sec = m.group('section')[:1100]
            vals = re.findall(r'(?<!\d)\d{1,3}(?:[.\s]\d{3})*,\d{2}(?!\d)', sec)
            if len(vals) >= 4 and re.search(r'VALOR\s+L[ÍI]QUIDO', sec, re.I):
                amount = _money(vals[3])
    output = {
        'number': number, 'series': series, 'issuer_name': name,
        'trade_name': '', 'issuer_document': re.sub(r'\D', '', doc.group(1)) if doc else '',
        'total_value': amount, 'access_key': '', 'description': '',
        'source': 'OCR', 'raw_text': text[:12000],
        'warnings': ['NFS-e municipal: confira os dados reconhecidos antes de salvar.'],
    }
    for key, field in [('number', 'número'), ('issuer_name', 'razão social'), ('issuer_document', 'CPF/CNPJ do emitente'), ('total_value', 'valor líquido')]:
        if not output[key]:
            output['warnings'].append(f'Não foi possível reconhecer {field}; confira manualmente.')
    return output


_before_municipal_parse = _parse_ocr_text

def _parse_ocr_text(text):
    municipal = _parse_nfse_municipal(text)
    if municipal is not None:
        return municipal
    return _before_municipal_parse(text)


# A versão inicial do OCR de fotos da NFS-e passa diretamente pelo parser
# nacional; esta segunda etapa corrige apenas o retorno municipal.
_before_municipal_image = _read_image

def _read_image(upload):
    result = _before_municipal_image(upload)
    municipal = _parse_nfse_municipal(result.get('raw_text', ''))
    if municipal is not None:
        return municipal
    return result


# Complementa a OCR de PDFs digitalizados com um recorte do campo número/série.
# A leitura da página inteira frequentemente transforma "3737 / U" em "a7371U".
_before_municipal_pdf = _read_pdf

def _read_pdf(upload):
    result = _before_municipal_pdf(upload)
    if not _parse_nfse_municipal(result.get('raw_text', '')):
        return result
    if result.get('number'):
        return result
    try:
        import pypdfium2 as pdfium
        import pytesseract
        from PIL import ImageOps
        upload.seek(0)
        document = pdfium.PdfDocument(upload.read())
        if len(document) != 1:
            document.close()
            return result
        page = document[0]
        image = page.render(scale=3).to_pil().convert('RGB')
        page.close()
        document.close()
        # Cabeçalho da NFS-e municipal: número / série na parte superior.
        region = image.crop((int(image.width*.1), int(image.height*.1),
                             int(image.width*.65), int(image.height*.22)))
        head = pytesseract.image_to_string(ImageOps.grayscale(region), lang='por+eng', config='--psm 11')
        m = re.search(r'(?<!\d)(\d{2,8})\s*/\s*([A-Z0-9]{1,3})(?!\w)', head, re.I)
        if m and not re.fullmatch(r'(?:19|20)\d{2}', m.group(1)):
            result['number'], result['series'] = m.group(1), m.group(2).upper()
            result['warnings'] = [w for w in result['warnings'] if 'número' not in w]
    except Exception:
        # Um recorte OCR auxiliar não deve impedir o upload do documento.
        pass
    return result

# Faturas comerciais de locação não são NF-e/NFS-e. Suporte de leitura
# documental para cadastro assistido, sem declarar validade fiscal.
def _parse_fatura_locacao(text):
    upper = text.upper()
    if not (re.search(r'FATURA\s+DE\s+LOCA[CÇ][ÃA]O', upper) and
            re.search(r'(?:BENS\s+M[ÓO]VEIS|LOCA[CÇ][ÃA]O|EQUIPAMENTOS)', upper)):
        return None
    lines = [_clean_line(line) for line in text.splitlines() if line.strip()]
    # O bloco do locador aparece antes de DESTINATÁRIO / FATURA.
    start = 0
    for i, line in enumerate(lines):
        if re.search(r'FATURA\s+DE\s+LOCA[CÇ][ÃA]O', line, re.I):
            start = i
            break
    vendor = lines[:max(start + 1, 10)]
    issuer_name = ''
    for line in vendor:
        match = re.search(r'(?:^|\s)([\wÀ-ÿ .&-]{6,90}\b(?:LTDA\.?|S/?A\.?|EIRELI))\b', line, re.I)
        if match and not re.search(r'ENDERE[CÇ]O|DESTINAT[ÁA]RIO', line, re.I):
            issuer_name = _clean_line(match.group(1))
            break
    if not issuer_name:
        # Algumas digitalizações dividem o nome e a forma societária.
        for line in lines[:8]:
            if 'LOCA' in line.upper() and 'FATURA' not in line.upper() and len(line) > 12:
                issuer_name = line
                break
    number = ''
    for pattern in [r'(?<!\d)N[º°o.]?\s*(\d{3,12})\b',
                    r'(?:FATURA\s*)?(?:N[ÚU]MERO|N[º°])\s*[:#-]?\s*(\d{3,12})\b']:
        for line in lines[:30]:
            m = re.search(pattern, line, re.I)
            if m:
                number = m.group(1)
                break
        if number:
            break
    # OCR alternativo costuma preservar o cabeçalho do locador melhor.
    match = re.search(r'(?im)^.{0,8}(CPL\s+LOCA[CÇ][ÃA]O\s+DE\s+M[ÁA]QUINAS\s+E\s+EQUIPAMENTOS\s+LTD[Aa]?\.?)(?=\s|$)', text)
    if match:
        issuer_name = _clean_line(match.group(1))
    if not number:
        # O número pode aparecer na mesma linha de FATURA / VALOR,
        # com a legenda "Nº" perdida pelo OCR.
        for i, line in enumerate(lines):
            if re.fullmatch(r'FATURA.*', line, re.I):
                nearby = ' '.join(lines[i:i+4])
                m = re.search(r'(?<!\d)(\d{5,10})(?!\d)\s+(?:(?:VALOR|R\$)|\d{2,4}[.,]\d{2})', nearby, re.I)
                if m:
                    number = m.group(1)
                    break
    # Não usar valor de item como total; exigir contexto de TOTAL ou VALOR da fatura.
    amount = None
    for line in lines:
        m = re.search(r'(?:VALOR\s+TOTAL|TOTAL\s*(?:R\$)?|VALOR\s*[:\-])\s*(?:R\$)?\s*([\d.]+,\d{2})', line, re.I)
        if m:
            amount = _money(m.group(1))
            break
    if amount is None:
        for i, line in enumerate(lines[:-1]):
            if re.search(r'VALOR\s+TOTAL\s*(?:R\$)?\s*$', line, re.I):
                m = re.search(r'(?<!\d)([\d.]+,\d{2})(?!\d)', lines[i + 1])
                if m:
                    amount = _money(m.group(1))
                    break
    issuer_doc = ''
    # Apenas documento identificado no cabeçalho do locador, nunca no bloco do destinatário.
    head = '\n'.join(lines[:next((i for i,l in enumerate(lines) if re.search(r'DESTINAT[ÁA]RIO', l, re.I)), len(lines))])
    d = re.search(r'(?<!\d)(\d{2}[.\s]?\d{3}[.\s]?\d{3}[/\s]?\d{4}[-\s]?\d{2})(?!\d)', head)
    if d:
        issuer_doc = re.sub(r'\D', '', d.group(1))
    output = {'number': number, 'series': '', 'issuer_name': issuer_name,
              'trade_name': '', 'issuer_document': issuer_doc, 'total_value': amount,
              'access_key': '', 'description': 'Fatura de locação de bens móveis',
              'source': 'OCR', 'raw_text': text[:12000],
              'warnings': ['Fatura de locação: documento comercial, não é NF-e ou NFS-e. Confira os dados antes de salvar.']}
    for field, name in [('number','número'),('issuer_name','locador'),('issuer_document','CPF/CNPJ do locador'),('total_value','valor total')]:
        if not output[field]:
            output['warnings'].append('Não foi possível reconhecer '+name+'; confira manualmente.')
    return output

_before_rental_parse = _parse_ocr_text

def _parse_ocr_text(text):
    rental = _parse_fatura_locacao(text)
    return rental if rental is not None else _before_rental_parse(text)

_before_rental_image = _read_image

def _read_image(upload):
    result = _before_rental_image(upload)
    return _parse_fatura_locacao(result.get('raw_text','')) or result

_before_rental_pdf = _read_pdf

def _read_pdf(upload):
    result = _before_rental_pdf(upload)
    return _parse_fatura_locacao(result.get('raw_text','')) or result

# Consolidação por papéis fiscais e contexto, não por município ou fornecedor.
_PREVIOUS_PARSE_DOCUMENT = _parse_ocr_text
_PREVIOUS_READ_DOCUMENT_IMAGE = _read_image
_PREVIOUS_READ_DOCUMENT_PDF = _read_pdf


def _service_issuer_block(text):
    """Somente prestador/emitente; nunca o tomador."""
    start = re.search(r'(?im)^\s*(?:EMITENTE\s+DA\s+NFS\S*|PRESTADOR\s+DE\s+SERVI[CÇ]O)\s*$', text)
    if not start:
        start = re.search(r'(?im)^\s*(?:EMITENTE\s+DA\s+NFS\S*|PRESTADOR\s+DE\s+SERVI[CÇ]O)\b', text)
    if not start:
        return ''
    tail = text[start.end():]
    end = re.search(r'(?im)^\s*(?:TOMADOR\s+(?:DO|DE)\s+SERVI[CÇ]O|DESTINAT[ÁA]RIO)\b', tail)
    return tail[:end.start()] if end else tail[:1800]


def _service_fiscal_enrichment(text, result):
    if not re.search(r'NFS\s*[-–.]?\s*[eE]|NOTA\s+FISCAL\s+DE\s+SERVI', text, re.I):
        return result
    if _parse_fatura_locacao(text) is not None:
        return result
    block = _service_issuer_block(text)
    # Não aceitar o e-mail como nome. Preferir a linha após Nome/Razão Social,
    # ou o nome empresarial identificado dentro do bloco do prestador.
    if block:
        # Valida novamente o CPF/CNPJ: parsers anteriores podem capturar o tomador.
        if result.get('issuer_document') and result['issuer_document'] not in re.sub(r'\D', '', block):
            result['issuer_document'] = ''
        name = ''
        lines = [_clean_line(x) for x in block.splitlines() if _clean_line(x)]
        for i, ln in enumerate(lines):
            m = re.search(r'(?:NOME\s*/\s*RAZ[ÃA]O\s+SOCIAL|NOME\s*/\s*NOME|NOME\s+EMPRESARIAL|RAZ[ÃA]O\s+SOCIAL)\s*[:\-]?\s*(.*)', ln, re.I)
            if not m:
                continue
            candidates = [m.group(1), *lines[i+1:i+3]]
            for candidate in candidates:
                candidate = re.split(r'\s+(?:E\s*-?\s*MAIL|INSCRI[CÇ][ÃA]O|ENDERE[CÇ]O)\b', candidate, 1, flags=re.I)[0].strip(' |-:')
                if (len(candidate) >= 7 and re.search(r'[A-Za-zÀ-ÿ]{3}', candidate)
                    and not re.search(r'@|\.com\b|\b(?:E\s*-?\s*MAIL|CPF|CNPJ|INSCRI[CÇ][ÃA]O|ENDERE[CÇ]O|NOME|MUNIC[IÍ]PIO)\b', candidate, re.I)):
                    name = candidate
                    break
            if name:
                break
        if name and (not result.get('issuer_name') or re.search(r'@|\.com\b|financeiro',result['issuer_name'], re.I)):
            result['issuer_name'] = name
        # CNPJ/CPF só pode sair da região de emitente.
        if not result.get('issuer_document'):
            document = re.search(r'(?<!\d)(\d{2}[.,]\d{3}[.,]\d{3}[/\s]\d{4}[-\s]\d{2}|\d{3}[.,]\d{3}[.,]\d{3}[-\s]\d{2})(?!\d)', block)
            if document:
                result['issuer_document'] = re.sub(r'\D', '', document.group(1))
    # Número da NFS-e nas variações 'NFS-e 673', 'Número da NFS-e 11',
    # 'Número/Série 3737/U'. Não buscar outros números sem rótulo.
    if not result.get('number'):
        head = text[:max(500, text.find(block))] if block else text[:1300]
        rules = [
            r'(?im)^\s*NFS\s*[-–.]?\s*[eE]\s*[:#º°-]?\s*(\d{1,12})\s*$',
            r'(?im)N[ÚU]MERO\s+DA\s+NFS\s*[-–.]?\s*[eE]?\s*[:#º°\-]*\s*(\d{1,12})\b',
            r'(?im)N[ÚU]MERO\s*/\s*S[ÉE]RIE\s*[:#º°\-]*\s*(\d{1,12})\s*[/|]\s*([A-Za-z0-9]{1,4})',
        ]
        for pattern in rules:
            match = re.search(pattern, head, re.I)
            if match:
                result['number'] = match.group(1)
                if match.lastindex and match.lastindex > 1:
                    result['series'] = match.group(2)
                break
    # Se a tabela possui rótulos e valores em colunas, a última célula
    # corresponde ao valor líquido; não confundir com imposto e valor bruto.
    if result.get('total_value') is None:
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if re.search(r'VALOR\s+L[IÍ]QUIDO\s*\(R\$\)', line, re.I):
                same = re.search(r'VALOR\s+L[IÍ]QUIDO\s*\(R\$\)\s*[:\-]?\s*(?:R\$\s*)?(\d{1,3}(?:[.]\d{3})*,\d{2})', line, re.I)
                if same:
                    result['total_value'] = _money(same.group(1))
                    break
                # Pode estar em linha própria abaixo de cabeçalho multicoluna.
                for nearby in lines[i+1:i+3]:
                    values = re.findall(r'(?<!\d)\d{1,3}(?:\.\d{3})*,\d{2}(?!\d)', nearby)
                    if len(values) >= 3:
                        result['total_value'] = _money(values[-1])
                        break
                if result.get('total_value') is not None:
                    break
        if result.get('total_value') is None:
            # Alternativa: tabela com Valor do Serviço e Valor Líquido,
            # sem textos intercalados dos impostos.
            m = re.search(r'(?im)^\s*VALOR\s+L[IÍ]QUIDO\s*[:\-]?\s*(?:DA\s+NFS\s*[-.]?e)?\s*(?:R\$)?\s*([\d.]+,\d{2})\s*$', text)
            if m:
                result['total_value'] = _money(m.group(1))
    result['warnings'] = [w for w in result.get('warnings', []) if not (
        ('número' in w.lower() and result.get('number')) or
        ('razão social' in w.lower() and result.get('issuer_name')) or
        ('nome do prestador' in w.lower() and result.get('issuer_name')) or
        ('valor' in w.lower() and result.get('total_value') is not None) or
        ('cpf/cnpj' in w.lower() and result.get('issuer_document'))
    )]
    return result


def _parse_ocr_text(text):
    return _service_fiscal_enrichment(text, _PREVIOUS_PARSE_DOCUMENT(text))


def _read_image(upload):
    result = _PREVIOUS_READ_DOCUMENT_IMAGE(upload)
    # Uma segunda leitura focada no cabeçalho ajuda em números pequenos
    # como '11' e '673', que desaparecem no OCR integral.
    raw = result.get('raw_text', '')
    if result.get('number') or not re.search(r'NFS\s*[-–.]?\s*e|DANFS', raw, re.I):
        return _service_fiscal_enrichment(raw, result)
    try:
        from PIL import Image, ImageOps, ImageEnhance
        import pytesseract
        upload.seek(0)
        img = ImageOps.exif_transpose(Image.open(upload)).convert('RGB')
        if img.width * img.height > 25_000_000:
            return result
        # Cabeçalho ocupa aproximadamente o primeiro quarto da página;
        # não usar DPS nem CNPJ como número sem rótulo.
        region = img.crop((int(img.width*.02), int(img.height*.04), int(img.width*.98), int(img.height*.30)))
        region = ImageOps.autocontrast(ImageOps.grayscale(region))
        if region.width < 2200:
            scale = 2200 / region.width
            region = region.resize((2200, max(1, round(region.height * scale))))
        header = pytesseract.image_to_string(region, lang='por+eng', config='--psm 6')
        candidate = _service_fiscal_enrichment(header, {'number':'','series':'','issuer_name':'', 'issuer_document':'','total_value':None,'warnings':[]})
        if candidate.get('number'):
            result['number'] = candidate['number']
            result['series'] = candidate.get('series', '')
    except Exception:
        pass
    return _service_fiscal_enrichment(raw, result)


def _read_pdf(upload):
    result = _PREVIOUS_READ_DOCUMENT_PDF(upload)
    return _service_fiscal_enrichment(result.get('raw_text', ''), result)


# Identificação adicional por regiões: aplicado somente após todos os leitores
# existentes. Nenhuma sequência numérica sem rótulo é aceita como nº fiscal.
_PRE_REGION_READ_IMAGE = _read_image


def _read_image(upload):
    result = _PRE_REGION_READ_IMAGE(upload)
    if result.get('number') or not re.search(r'NFS\s*[-–.]?\s*e|DANFS', result.get('raw_text', ''), re.I):
        return result
    try:
        from PIL import Image, ImageOps, ImageEnhance, ImageFilter
        import pytesseract
        upload.seek(0)
        image = ImageOps.exif_transpose(Image.open(upload)).convert('RGB')
        if image.width * image.height > 25_000_000:
            return result
        # Recortes relativos à página; rótulos são obrigatórios para aceitar
        # candidatos. Evita associar números de DPS, datas ou tributos à nota.
        regions = [(0.03, 0.06, 0.55, 0.22), (0.03, 0.07, 0.98, 0.27)]
        candidates = set()
        for x0, y0, x1, y1 in regions:
            crop = image.crop((int(image.width*x0), int(image.height*y0),
                               int(image.width*x1), int(image.height*y1)))
            gray = ImageOps.autocontrast(ImageOps.grayscale(crop))
            gray = ImageEnhance.Contrast(gray).enhance(1.7)
            factor = max(2, min(5, round(2700 / max(1, gray.width))))
            gray = gray.resize((gray.width*factor, gray.height*factor))
            for psm in (4, 6):
                extracted = pytesseract.image_to_string(gray, lang='por+eng', config=f'--psm {psm}')
                # Apenas o número que vem depois do rótulo da NFS-e.
                match = re.search(r'(?im)N[úu]mero\s+da\s+NFS\s*[-–.]?\s*e\s*[:#]?\s*\n?\s*(\d{1,12})\b', extracted)
                if match:
                    candidates.add(match.group(1))
        if len(candidates) == 1:
            result['number'] = candidates.pop()
            result['warnings'] = [w for w in result.get('warnings', []) if 'número' not in w.lower()]
    except (ImportError, OSError, ValueError):
        pass
    except Exception:
        # OCR opcional não pode impedir o restante da nota de ser preenchido.
        pass
    return result

# Última alternativa para DANFSe padrão nacional fotografado: segmentação
# de caracteres na célula do número, após falha do OCR textual. A estratégia
# é restrita a dois algarismos '1' visualmente isolados e semelhantes;
# outros números continuam sujeitos à conferência humana.
_PRE_STROKE_IMAGE = _read_image


def _national_short_number_from_strokes(image):
    """Lê '11' por forma dos glifos na célula de número do DANFSe v1.0.

    Não depende de cidade, CPF, nome do emitente ou número fiscal pré-definido.
    Só aceita dois componentes estreitos, idênticos e sem símbolos adjacentes.
    """
    try:
        import cv2
        import numpy as np
        from PIL import ImageOps
        im = ImageOps.exif_transpose(image).convert('L')
        width, height = im.size
        # Posição documentada do campo no DANFSe nacional (não de prefeituras).
        # Sem confiança geométrica suficiente, não é emitido candidato.
        x0, x1 = round(width * .053), round(width * .095)
        y0, y1 = round(height * .1045), round(height * .118)
        pixels = np.array(im.crop((x0, y0, x1, y1)))
        if pixels.size == 0:
            return ''
        _, mask = cv2.threshold(pixels, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        shapes = []
        for x, y, w, h, area in stats[1:]:
            if h >= (y1-y0)*.30 and 2 <= w <= h*.7 and area >= 7 and area/(w*h) >= .33:
                shapes.append((int(x), int(y), int(w), int(h), int(area)))
        shapes.sort()
        if len(shapes) != 2:
            return ''
        first, second = shapes
        same_baseline = abs((first[1]+first[3])-(second[1]+second[3])) <= 2
        similar = abs(first[3]-second[3]) <= 2 and abs(first[2]-second[2]) <= 2
        spacing = 1 <= second[0]-(first[0]+first[2]) <= max(7, first[2]*2)
        return '11' if same_baseline and similar and spacing else ''
    except (ImportError, ValueError, OSError):
        return ''


def _read_image(upload):
    result = _PRE_STROKE_IMAGE(upload)
    if result.get('number'):
        return result
    raw = result.get('raw_text', '')
    # Somente DANFSe nacional com o cabeçalho padrão. Não aplicar a NF-e,
    # à NFS-e municipal ou à fatura de locação.
    if not re.search(r'DANFS[EO]|Documento Auxiliar da NFS', raw, re.I):
        return result
    try:
        from PIL import Image
        upload.seek(0)
        with Image.open(upload) as im:
            number = _national_short_number_from_strokes(im)
        if number:
            result['number'] = number
            result['warnings'] = [w for w in result.get('warnings', []) if 'número' not in w.lower()]
            result['warnings'].append('Número identificado por segmentação visual: confirme antes de salvar.')
    except (OSError, ValueError):
        pass
    return result

# Complemento genérico: DANFSe com cabeçalho do emitente danificado pelo OCR.
# Não depende de município, fornecedor ou número de documento de exemplo.
_PRE_FLEX_PARSE = _parse_ocr_text
_PRE_FLEX_IMAGE = _read_image
_PRE_FLEX_PDF = _read_pdf


def _flex_service_fields(text, result):
    if not re.search(r'DANFS|NFS\s*[-.]?\s*[eE]|NOTA FISCAL DE SERVI', text, re.I):
        return result
    if _parse_fatura_locacao(text) is not None:
        return result

    # Em OCR danificado, 'EMITENTE DA NFS-e' pode sumir, mas o início da
    # seção ainda contém 'Prestador do Serviço'. O tomador delimita a seção.
    marker = re.search(r'(?im)^\s*(?:PRESTADOR\s+DO\s+SERVI[CÇ]O|EMITENTE\s+DA\s+NFS\S*)', text)
    if marker:
        remainder = text[marker.start():]
        end = re.search(r'(?im)^\s*TOMADOR\s+(?:DO|DE)\s+SERVI[CÇ]O', remainder)
        issuer = remainder[:end.start()] if end else remainder[:1700]
        # Evitar que o fornecedor seja confundido com e-mail ou tomador.
        if not result.get('issuer_name'):
            lines = [re.sub(r'\s+', ' ', line).strip() for line in issuer.splitlines()]
            for index, line in enumerate(lines):
                if re.search(r'\bNOME\s*[/|]\s*(?:NOME\s+)?EMPRESARIAL\b|\bNOME\s*[/|]\s*RAZ[ÃA]O', line, re.I):
                    for candidate in lines[index + 1:index + 3]:
                        candidate = re.split(r'\s+(?:\S+@\S+|E-?MAIL\b|ENDERE[CÇ]O\b)', candidate, 1, flags=re.I)[0].strip(' -|')
                        if (len(candidate) >= 8 and re.search(r'[A-ZÀ-Ý]{3}', candidate, re.I)
                                and not re.search(r'@|\b(?:NOME|E-?MAIL|CPF|CNPJ|RUA|CEP)\b', candidate, re.I)):
                            result['issuer_name'] = candidate
                            break
                    if result.get('issuer_name'):
                        break
        if not result.get('issuer_document'):
            # Tolera 43.834 493/0001-78, mas exige 14 dígitos depois da limpeza.
            for match in re.finditer(r'(?<!\d)\d{2}\s*[., ]\s*\d{3}\s*[., ]\s*\d{3}\s*[/ ]\s*\d{4}\s*[- ]\s*\d{2}(?!\d)', issuer):
                number = re.sub(r'\D', '', match.group())
                if len(number) == 14:
                    result['issuer_document'] = number
                    break

    if result.get('total_value') is None:
        # Aceita rótulo/valor em linhas distintas; exige moeda explícita.
        # Busca a última ocorrência de valor líquido para ignorar tabelas
        # anteriores que contêm alíquotas e outras retenções.
        matches = list(re.finditer(
            r'VALOR\s+L[IÍ]QUIDO\s+DA\s+NFS\s*[-.]?\s*E\b', text, re.I
        ))
        for match in reversed(matches):
            tail = text[match.end():match.end() + 110]
            money_match = re.search(r'R\$\s*(\d{1,3}(?:[.\s]\d{3})*,\d{2})\b', tail)
            if money_match:
                result['total_value'] = _money(money_match.group(1))
                break

    recovered = {'number': 'número', 'issuer_name': 'nome do prestador',
                 'issuer_document': 'CPF/CNPJ do prestador', 'total_value': 'valor'}
    result['warnings'] = [warning for warning in result.get('warnings', [])
                          if not any((result.get(key) is not None if key == 'total_value' else bool(result.get(key)))
                                     and label.lower() in warning.lower() for key, label in recovered.items())]
    return result


def _parse_ocr_text(text):
    return _flex_service_fields(text, _PRE_FLEX_PARSE(text))


def _read_image(upload):
    result = _PRE_FLEX_IMAGE(upload)
    return _flex_service_fields(result.get('raw_text', ''), result)


def _read_pdf(upload):
    result = _PRE_FLEX_PDF(upload)
    return _flex_service_fields(result.get('raw_text', ''), result)
