from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import (
    ParagraphStyle,
    getSampleStyleSheet,
)
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from memorando_remessas.models import ShipmentMemo


class ShipmentMemoPdfError(Exception):
    """Erro ao gerar o PDF do memorando de remessa."""


def _safe(value) -> str:
    return escape(str(value or "-"))


def _format_date(value) -> str:
    if not value:
        return "-"

    return value.strftime("%d/%m/%Y")


def _get_user_name(user) -> str:
    if not user:
        return "-"

    return (
        getattr(user, "name", None)
        or user.get_full_name()
        or getattr(user, "username", None)
        or str(user)
    )


def generate_shipment_memo_pdf(
    *,
    shipment_memo: ShipmentMemo,
) -> bytes:
    buffer = BytesIO()

    try:
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=18 * mm,
            leftMargin=18 * mm,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            title=shipment_memo.code or "Memorando de Remessa",
            author="Daruix Engenharia",
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "ShipmentMemoTitle",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontSize=16,
            leading=20,
            spaceAfter=4 * mm,
        )

        subtitle_style = ParagraphStyle(
            "ShipmentMemoSubtitle",
            parent=styles["Normal"],
            alignment=TA_CENTER,
            fontSize=9,
            textColor=colors.HexColor("#5D6677"),
            spaceAfter=6 * mm,
        )

        section_style = ParagraphStyle(
            "ShipmentMemoSection",
            parent=styles["Heading2"],
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#A00D0E"),
            spaceBefore=4 * mm,
            spaceAfter=2 * mm,
        )

        normal_style = ParagraphStyle(
            "ShipmentMemoNormal",
            parent=styles["Normal"],
            fontSize=9,
            leading=13,
        )

        story = [
            Paragraph(
                "MEMORANDO DE REMESSA",
                title_style,
            ),
            Paragraph(
                (
                    f"{_safe(shipment_memo.code)} "
                    f"— Revisão {shipment_memo.revision}"
                ),
                subtitle_style,
            ),
        ]

        identification_data = [
            [
                Paragraph("<b>Centro de custo</b>", normal_style),
                Paragraph(_safe(shipment_memo.cost_center), normal_style),
            ],
            [
                Paragraph("<b>Obra</b>", normal_style),
                Paragraph(_safe(shipment_memo.work_name), normal_style),
            ],
            [
                Paragraph("<b>Cliente</b>", normal_style),
                Paragraph(_safe(shipment_memo.client_name), normal_style),
            ],
            [
                Paragraph("<b>Documento</b>", normal_style),
                Paragraph(_safe(shipment_memo.client_document), normal_style),
            ],
            [
                Paragraph("<b>Data da remessa</b>", normal_style),
                Paragraph(
                    _format_date(shipment_memo.shipping_date),
                    normal_style,
                ),
            ],
            [
                Paragraph("<b>Aos cuidados de</b>", normal_style),
                Paragraph(_safe(shipment_memo.attention_to), normal_style),
            ],
            [
                Paragraph("<b>Assunto</b>", normal_style),
                Paragraph(_safe(shipment_memo.subject), normal_style),
            ],
        ]

        identification_table = Table(
            identification_data,
            colWidths=[
                42 * mm,
                132 * mm,
            ],
            hAlign="LEFT",
        )

        identification_table.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, -1),
                    colors.HexColor("#F4F5F7"),
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.35,
                    colors.HexColor("#D7DAE0"),
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
            ])
        )

        story.append(identification_table)

        responsible_links = list(
            shipment_memo.responsible_links
            .select_related("user")
            .order_by(
                "-is_primary",
                "created_at",
                "id",
            )
        )

        if responsible_links:
            story.extend([
                Paragraph(
                    "Responsáveis",
                    section_style,
                ),
                Paragraph(
                    "<br/>".join(
                        (
                            f"{_safe(_get_user_name(link.user))}"
                            f"{' — principal' if link.is_primary else ''}"
                        )
                        for link in responsible_links
                    ),
                    normal_style,
                ),
            ])

        options = list(
            shipment_memo.options
            .all()
            .order_by(
                "option_type",
                "order",
                "name",
                "id",
            )
        )

        if options:
            story.extend([
                Paragraph(
                    "Documentos, finalidade e solicitações",
                    section_style,
                ),
                Paragraph(
                    "<br/>".join(
                        f"• {_safe(option.name)}"
                        for option in options
                    ),
                    normal_style,
                ),
            ])

        story.extend([
            Paragraph(
                "Observações",
                section_style,
            ),
            Paragraph(
                _safe(
                    shipment_memo.notes
                    or "Sem observações."
                ).replace("\n", "<br/>"),
                normal_style,
            ),
            Spacer(
                1,
                8 * mm,
            ),
            Paragraph(
                (
                    "Emitido pelo Daruix Hub. "
                    f"Criado por: "
                    f"{_safe(_get_user_name(shipment_memo.created_by))}."
                ),
                ParagraphStyle(
                    "ShipmentMemoFooter",
                    parent=normal_style,
                    fontSize=8,
                    textColor=colors.HexColor("#6E7685"),
                ),
            ),
        ])

        document.build(story)

        return buffer.getvalue()

    except Exception as error:
        raise ShipmentMemoPdfError(
            "Não foi possível gerar o PDF do memorando."
        ) from error

    finally:
        buffer.close()
