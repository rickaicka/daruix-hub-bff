from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from pathlib import Path
import os
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from memorando_remessas.models import ShipmentMemo


class ShipmentMemoPdfError(Exception):
    """Erro ao gerar o PDF do memorando de remessa."""


MONTHS_PT = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}

COMPANY_NAME = "R.S. DARUIX ENGENHARIA LTDA."
CITY_NAME = "São Paulo"
CONTACT_LINE_1 = (
    "Rua Antonio Camardo 440 - Tatuapé - S.P. - CEP 03039-060 - "
    "Fone/Fax (11) 3255 8570 - 3151 3019 - 3151 3024 / 3151 3033"
)
CONTACT_LINE_2 = "Email : daruix@daruix.com.br"

LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "daruix_logo.png"


def _safe_text(value: object | None) -> str:
    return str(value or "").strip()


def _truncate(text: str, length: int) -> str:
    text = _safe_text(text)
    if len(text) <= length:
        return text
    return text[: max(0, length - 3)].rstrip() + "..."


def _format_date(value) -> str:
    if not value:
        return ""
    return value.strftime("%d/%m/%Y")


def _format_date_extenso(value) -> str:
    if not value:
        return ""
    return f"{CITY_NAME}, {value.day:02d} de {MONTHS_PT.get(value.month, '')}, {value.year}"


def _format_currency(value: Decimal | None) -> str:
    if value is None:
        return ""
    try:
        number = Decimal(value)
    except Exception:
        return _safe_text(value)
    integer, decimal = f"{number:.2f}".split(".")
    grouped = []
    while integer:
        grouped.append(integer[-3:])
        integer = integer[:-3]
    return ".".join(reversed(grouped)) + "," + decimal


# Fontes devem ser instaladas no backend; ReportLab nao carrega CSS/woff do Angular.
# Prioridade: paths de ambiente; depois arquivos TTF locais de assets/fonts.
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def _register_custom_fonts() -> dict[str, str]:
    """Registra as fontes TTF reais do Hub presentes em assets/fonts.

    Variáveis MR_FONT_*_PATH continuam disponíveis para sobrescrever caminhos.
    Usa Helvetica somente quando a fonte correspondente não existir ou falhar.
    """
    result = {
        "heading": "Helvetica", "heading_bold": "Helvetica-Bold",
        "heading_semibold": "Helvetica-Bold",
        "body": "Helvetica", "body_medium": "Helvetica",
        "body_semibold": "Helvetica-Bold", "body_bold": "Helvetica-Bold",
    }
    candidates = {
        "heading": ("MR_FONT_GOTHIC_PATH", "ScienceGothic-Regular.ttf", "MRScienceGothic"),
        "heading_bold": ("MR_FONT_GOTHIC_BOLD_PATH", "ScienceGothic-Bold.ttf", "MRScienceGothicBold"),
        "heading_semibold": (None, "ScienceGothic-SemiBold.ttf", "MRScienceGothicSemiBold"),
        "body": ("MR_FONT_QUICKSAND_PATH", "Quicksand-Regular.ttf", "MRQuicksand"),
        "body_medium": (None, "Quicksand-Medium.ttf", "MRQuicksandMedium"),
        "body_semibold": (None, "Quicksand-SemiBold.ttf", "MRQuicksandSemiBold"),
        "body_bold": ("MR_FONT_QUICKSAND_BOLD_PATH", "Quicksand-Bold.ttf", "MRQuicksandBold"),
    }
    for key, (env_key, filename, font_name) in candidates.items():
        explicit = os.environ.get(env_key) if env_key else None
        path = Path(explicit) if explicit else FONT_DIR / filename
        if not path.is_file():
            continue
        try:
            if font_name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(font_name, str(path)))
            result[key] = font_name
        except Exception:
            # Mantém a geração do documento com uma fonte substituta.
            continue
    if result["heading_semibold"] == "Helvetica-Bold":
        result["heading_semibold"] = result["heading_bold"]
    if result["body_medium"] == "Helvetica":
        result["body_medium"] = result["body"]
    if result["body_semibold"] == "Helvetica-Bold":
        result["body_semibold"] = result["body_bold"]
    return result


def _fit_text(text: str, font_name: str, font_size: float, max_width: float) -> str:
    """Evita texto ultrapassando as células depois da troca da tipografia."""
    text = _safe_text(text)
    if pdfmetrics.stringWidth(text, font_name, font_size) <= max_width:
        return text
    suffix = "..."
    while text and pdfmetrics.stringWidth(text + suffix, font_name, font_size) > max_width:
        text = text[:-1]
    return text.rstrip() + suffix if text else suffix


def _draw_logo(pdf: canvas.Canvas, page_width: float, top_y: float) -> None:
    if not LOGO_PATH.exists():
        return
    try:
        reader = ImageReader(str(LOGO_PATH))
        img_w = 28 * mm
        img_h = 28 * mm
        x = page_width - 18 * mm - img_w
        y = top_y - img_h + 2 * mm
        pdf.drawImage(reader, x, y, width=img_w, height=img_h, mask='auto', preserveAspectRatio=True)
    except Exception:
        return


def _draw_header(pdf: canvas.Canvas, shipment_memo: ShipmentMemo, page_width: float, page_height: float) -> float:
    left = 18 * mm
    top = page_height - 16 * mm

    _draw_logo(pdf, page_width, top + 4 * mm)

    text_x = left
    pdf.setFillColor(colors.black)
    pdf.setFont(pdf._mr_fonts["heading_bold"], 10.5)
    pdf.drawString(text_x, top - 2 * mm, COMPANY_NAME)
    pdf.setFont(pdf._mr_fonts["heading_bold"], 8.8)
    pdf.drawString(text_x, top - 9 * mm, "MEMORANDO DE REMESSA")
    pdf.setFont(pdf._mr_fonts["body"], 8.6)
    pdf.drawString(text_x, top - 16 * mm, _format_date_extenso(shipment_memo.shipping_date))

    subject = f"NOTAS FISCAIS - {shipment_memo.cost_center or shipment_memo.code or ''}".strip(" -")
    pdf.setFont(pdf._mr_fonts["heading_bold"], 9)
    pdf.drawString(text_x, top - 25 * mm, f"ASSUNTO:  {subject}")

    pdf.setFont(pdf._mr_fonts["body"], 8.7)
    pdf.drawString(text_x, top - 32 * mm, "Remetemos o(s) documento(s) abaixo relacionado(s)")

    return top - 37 * mm


def _draw_species_finality(pdf: canvas.Canvas, start_y: float, usable_width: float) -> float:
    left = 18 * mm
    species_w = 78 * mm
    finality_w = usable_width - species_w
    header_h = 6 * mm
    row_h = 6 * mm

    pdf.setLineWidth(0.5)
    pdf.setFont(pdf._mr_fonts["heading_semibold"], 8.3)
    pdf.rect(left, start_y - header_h, species_w, header_h)
    pdf.rect(left + species_w, start_y - header_h, finality_w, header_h)
    pdf.drawCentredString(left + species_w / 2, start_y - header_h + 1.9 * mm, "ESPÉCIE")
    pdf.drawCentredString(left + species_w + finality_w / 2, start_y - header_h + 1.9 * mm, "FINALIDADE")

    y = start_y - header_h
    pdf.rect(left, y - row_h, 7 * mm, row_h)
    pdf.rect(left + 7 * mm, y - row_h, species_w - 7 * mm, row_h)
    pdf.rect(left + species_w, y - row_h, finality_w, row_h)
    pdf.setFont(pdf._mr_fonts["body"], 8.1)
    pdf.drawCentredString(left + 3.5 * mm, y - row_h + 1.7 * mm, "X")
    pdf.drawString(left + 9 * mm, y - row_h + 1.7 * mm, "Notas Fiscais")
    pdf.drawString(left + species_w + 4 * mm, y - row_h + 1.7 * mm, "Para Devolução")
    return y - row_h - 4 * mm


TABLE_HEADERS = ["Doc. N°", "Descrição", "Rev."]
TABLE_COL_WIDTHS = [32 * mm, 119 * mm, 15 * mm]
TABLE_ROW_H = 5.8 * mm
TABLE_HEADER_H = 6.5 * mm
TABLE_MAX_ROWS_FIRST_PAGE = 17
TABLE_MAX_ROWS_NEXT_PAGE = 23


def _invoice_row(invoice) -> list[str]:
    number = _safe_text(invoice.number)
    prefix = "NF"
    if invoice.description and "serv" in invoice.description.lower():
        prefix = "NFS"
    if invoice.trade_name and prefix == "NF":
        # nothing special, preserve default label
        pass
    description_parts = [prefix]
    if number:
        description_parts.append(number)
    name = invoice.trade_name or invoice.issuer_name or ""
    if name:
        description_parts.append(name)
    desc = " ".join(part for part in description_parts if part)
    return [
        number,
        _truncate(desc.upper(), 46),
        _safe_text(invoice.series),
        _safe_text(invoice.source),
    ]


def _draw_table(pdf: canvas.Canvas, shipment_memo: ShipmentMemo, page_width: float, page_height: float, start_y: float) -> float:
    left = 18 * mm
    rows = [_invoice_row(invoice) for invoice in shipment_memo.invoices.all()]
    row_index = 0
    current_y = start_y
    first_page = True

    while row_index < max(len(rows), 1):
        if not first_page:
            pdf.showPage()
            current_y = _draw_header(pdf, shipment_memo, page_width, page_height)
            current_y = _draw_species_finality(pdf, current_y, page_width - 36 * mm)
        limit = TABLE_MAX_ROWS_FIRST_PAGE if first_page else TABLE_MAX_ROWS_NEXT_PAGE
        page_rows = rows[row_index: row_index + limit]
        while len(page_rows) < limit:
            page_rows.append(["", "", "", ""])

        header_y = current_y
        x = left
        pdf.setFont(pdf._mr_fonts["heading_semibold"], 7.9)
        for col, w in zip(TABLE_HEADERS, TABLE_COL_WIDTHS):
            pdf.rect(x, header_y - TABLE_HEADER_H, w, TABLE_HEADER_H)
            pdf.drawCentredString(x + w / 2, header_y - TABLE_HEADER_H + 1.9 * mm, _fit_text(col, pdf._mr_fonts["heading_semibold"], 7.9, w - 2 * mm))
            x += w

        y = header_y - TABLE_HEADER_H
        pdf.setFont(pdf._mr_fonts["heading_bold"], 8)
        for row in page_rows:
            x = left
            for idx, (cell, w) in enumerate(zip(row, TABLE_COL_WIDTHS)):
                pdf.rect(x, y - TABLE_ROW_H, w, TABLE_ROW_H)
                if idx == 0:
                    pdf.setFont(pdf._mr_fonts["heading_bold"], 8)
                else:
                    pdf.setFont(pdf._mr_fonts["body_medium"], 8 if idx == 1 else 7.8)
                if idx == 1:
                    pdf.drawString(x + 1.5 * mm, y - TABLE_ROW_H + 1.6 * mm, _fit_text(cell, pdf._mr_fonts["body_medium"], 8, w - 3 * mm))
                elif idx == 0:
                    number_font = pdf._mr_fonts["heading_bold"]
                    number_font_size = 8.0
                    while (number_font_size > 5.0 and
                           pdfmetrics.stringWidth(cell, number_font, number_font_size) > w - 3 * mm):
                        number_font_size -= 0.25
                    pdf.setFont(number_font, number_font_size)
                    pdf.drawCentredString(x + w / 2, y - TABLE_ROW_H + 1.6 * mm, cell)
                else:
                    pdf.setFont(pdf._mr_fonts["body"], 7.6)
                    pdf.drawCentredString(x + w / 2, y - TABLE_ROW_H + 1.6 * mm, _fit_text(cell, pdf._mr_fonts["heading_bold"] if idx == 0 else pdf._mr_fonts["body"], 8 if idx == 0 else 7.6, w - 2 * mm))
                x += w
            y -= TABLE_ROW_H

        row_index += limit
        current_y = y
        first_page = False
        if row_index >= len(rows):
            break
    return current_y


def _name_from_user(user) -> str:
    """Nome de exibição do usuário autenticado, sem supor um modelo específico."""
    if not user:
        return ""
    for attr in ("name", "full_name"):
        value = getattr(user, attr, None)
        if value:
            return _safe_text(value)
    get_full_name = getattr(user, "get_full_name", None)
    if callable(get_full_name):
        value = get_full_name()
        if value:
            return _safe_text(value)
    first = _safe_text(getattr(user, "first_name", ""))
    last = _safe_text(getattr(user, "last_name", ""))
    return f"{first} {last}".strip() or _safe_text(getattr(user, "username", ""))


def _draw_signature_block(
    pdf: canvas.Canvas,
    shipment_memo: ShipmentMemo,
    start_y: float,
    page_width: float,
    *,
    generated_by=None,
) -> None:
    """Duas assinaturas: responsável do Hub e recebedor com nome manuscrito."""
    left_margin = 18 * mm
    right_margin = page_width - 18 * mm
    gap = 16 * mm
    usable = right_margin - left_margin
    signature_width = (usable - gap) / 2
    left_x = left_margin
    right_x = left_margin + signature_width + gap
    line_y = start_y - 11 * mm

    # Respeitar a área do rodapé institucional.
    if line_y < 41 * mm:
        line_y = 41 * mm

    pdf.setStrokeColor(colors.black)
    pdf.setLineWidth(0.65)
    pdf.line(left_x, line_y, left_x + signature_width, line_y)
    pdf.line(right_x, line_y, right_x + signature_width, line_y)

    responsible = (
        _name_from_user(generated_by)
        or _name_from_user(getattr(shipment_memo, "created_by", None))
    )
    if not responsible:
        link = (
            shipment_memo.responsible_links.select_related("user")
            .order_by("-is_primary", "created_at")
            .first()
        )
        responsible = _name_from_user(link.user) if link else ""

    caption_font = pdf._mr_fonts["body_semibold"]
    pdf.setFont(caption_font, 8)
    pdf.drawCentredString(
        left_x + signature_width / 2,
        line_y - 5 * mm,
        "Recebido na obra por:",
    )
    pdf.drawCentredString(
        right_x + signature_width / 2,
        line_y - 5 * mm,
        "Recebido por:",
    )
    if responsible:
        name = _safe_text(responsible)
        font_name = pdf._mr_fonts["body_medium"]
        size = 8
        while size > 6 and pdfmetrics.stringWidth(name, font_name, size) > signature_width - 2 * mm:
            size -= 0.3
        pdf.setFont(font_name, size)
        pdf.drawCentredString(
            left_x + signature_width / 2,
            line_y - 10 * mm,
            name,
        )
    # O campo direito fica inteiramente livre para a assinatura e o nome manuscrito.

def _draw_footer(pdf: canvas.Canvas, page_width: float) -> None:
    left = 18 * mm
    footer_y = 18 * mm
    pdf.setFillColor(colors.HexColor("#A62525"))
    pdf.setFont(pdf._mr_fonts["body"], 6.7)
    pdf.drawCentredString(page_width / 2, footer_y + 4.5 * mm, CONTACT_LINE_1)
    pdf.drawCentredString(page_width / 2, footer_y, CONTACT_LINE_2)
    pdf.setFillColor(colors.black)


def generate_shipment_memo_pdf(*, shipment_memo: ShipmentMemo, generated_by=None) -> bytes:
    buffer = BytesIO()
    try:
        pdf = canvas.Canvas(buffer, pagesize=A4)
        pdf.setTitle(f"NF - {shipment_memo.cost_center or shipment_memo.code or 'Memorando'}")
        pdf.setAuthor("Daruix Engenharia")
        pdf.setSubject("Memorando de Remessa de Notas Fiscais")
        pdf._mr_fonts = _register_custom_fonts()
        page_width, page_height = A4

        start_y = _draw_header(pdf, shipment_memo, page_width, page_height)
        start_y = _draw_species_finality(pdf, start_y, page_width - 36 * mm)
        end_table_y = _draw_table(pdf, shipment_memo, page_width, page_height, start_y)
        # signature block only on last page
        min_sig_y = 56 * mm
        if end_table_y < min_sig_y:
            pdf.showPage()
            _draw_header(pdf, shipment_memo, page_width, page_height)
            end_table_y = 130 * mm
        _draw_signature_block(pdf, shipment_memo, max(end_table_y - 12 * mm, 72 * mm), page_width, generated_by=generated_by)
        _draw_footer(pdf, page_width)
        pdf.save()
        return buffer.getvalue()
    except Exception as error:
        raise ShipmentMemoPdfError("Não foi possível gerar o PDF do memorando.") from error
    finally:
        buffer.close()
