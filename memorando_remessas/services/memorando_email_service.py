from __future__ import annotations

from email.mime.image import MIMEImage
from html import escape
import logging
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from memorando_remessas.models import ShipmentMemo
from memorando_remessas.services.memorando_pdf_service import (
    ShipmentMemoPdfError,
    generate_shipment_memo_pdf,
)

logger = logging.getLogger(__name__)

LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "email" / "daruix_logo.png"
LOGO_CID = "daruix_logo_email"


class ShipmentMemoEmailError(Exception):
    """Erro ao montar ou enviar o memorando por e-mail."""


def _format_date(value) -> str:
    if not value:
        return "-"
    return value.strftime("%d/%m/%Y")


def _safe(value) -> str:
    return escape(str(value if value not in (None, "") else "-")).strip() or "-"


def _build_subject(shipment_memo: ShipmentMemo) -> str:
    return f"Memorando de Remessa {shipment_memo.code} - {shipment_memo.cost_center}"


def _build_text_body(shipment_memo: ShipmentMemo) -> str:
    lines = [
        f"Segue o Memorando de Remessa {shipment_memo.code}.",
        "",
        f"Revisão: {shipment_memo.revision}",
        f"Centro de custo: {shipment_memo.cost_center}",
        f"Obra: {shipment_memo.work_name}",
        f"Cliente: {shipment_memo.client_name}",
        f"Data da remessa: {_format_date(shipment_memo.shipping_date)}",
    ]
    if shipment_memo.received_by_name:
        lines.append(f"Recebido por: {shipment_memo.received_by_name}")
    if shipment_memo.received_at:
        lines.append(f"Data de recebimento: {_format_date(shipment_memo.received_at)}")
    if (shipment_memo.notes or "").strip():
        lines.extend(["", "Observações:", shipment_memo.notes])
    lines.extend(["", "O memorando em PDF está anexado a esta mensagem."])
    return "\n".join(lines)


def _build_html_body(shipment_memo: ShipmentMemo) -> str:
    def field(label: str, value, *, border: bool = True) -> str:
        rule = "border-bottom:1px solid #edf0f5;" if border else ""
        return (
            "<tr>"
            f"<td valign='top' style='width:170px;padding:13px 12px 13px 0;{rule}"
            "color:#687385;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:19px;'>"
            f"{_safe(label)}</td>"
            f"<td valign='top' style='padding:13px 0;{rule}"
            "color:#17233b;font-family:Arial,Helvetica,sans-serif;font-size:13px;"
            "line-height:20px;font-weight:bold;overflow-wrap:anywhere;'>"
            f"{_safe(value)}</td></tr>"
        )

    fields = [
        field("Centro de custo", shipment_memo.cost_center),
        field("Obra", shipment_memo.work_name),
        field("Cliente", shipment_memo.client_name),
        field("Data da remessa", _format_date(shipment_memo.shipping_date)),
    ]
    if shipment_memo.received_by_name:
        fields.append(field("Recebido na obra por", shipment_memo.received_by_name))
    if shipment_memo.received_at:
        fields.append(field("Data do recebimento", _format_date(shipment_memo.received_at), border=False))

    notes_html = ""
    if (shipment_memo.notes or "").strip():
        notes = _safe(shipment_memo.notes).replace("\n", "<br>")
        notes_html = (
            "<tr><td style='padding:0 32px 24px;'>"
            "<p style='margin:0 0 8px;color:#17233b;font-size:13px;font-weight:bold;font-family:Arial,Helvetica,sans-serif;'>"
            "Observações</p>"
            "<div style='padding:14px 16px;background:#f7f8fb;border:1px solid #e7eaf0;"
            "border-radius:6px;color:#4e5b6e;font-size:13px;line-height:21px;font-family:Arial,Helvetica,sans-serif;'>"
            f"{notes}</div></td></tr>"
        )

    code = _safe(shipment_memo.code)
    cost_center = _safe(shipment_memo.cost_center)
    revision = _safe(shipment_memo.revision)
    subject = f"NOTAS FISCAIS &nbsp;·&nbsp; {cost_center}"

    return f"""<!doctype html>
<html lang='pt-BR'>
<head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'></head>
<body style='margin:0;padding:0;background:#f2f4f8;'>
<table role='presentation' cellpadding='0' cellspacing='0' border='0' width='100%'
       style='width:100%;background:#f2f4f8;border-collapse:collapse;'>
  <tr><td align='center' style='padding:28px 12px;'>
    <table role='presentation' cellpadding='0' cellspacing='0' border='0' width='620'
           style='width:100%;max-width:620px;background:#fff;border-collapse:separate;border-spacing:0;'>
      <tr><td style='background:#bd111c;height:5px;font-size:1px;line-height:5px;'>&nbsp;</td></tr>
      <tr><td style='padding:16px 24px 14px;border-bottom:1px solid #e9ecf2;'>
        <table role='presentation' cellpadding='0' cellspacing='0' width='100%' style='border-collapse:collapse;'>
          <tr>
            <td valign='middle'>
              <img src='cid:{LOGO_CID}' alt='Daruix Engenharia' width='96' height='115' style='display:block;width:96px;max-width:96px;height:115px;border:0;outline:none;text-decoration:none;'>
            </td>
            <td valign='top' align='right' style='color:#738094;font-family:Arial,Helvetica,sans-serif;font-size:11px;letter-spacing:0.3px;padding-top:6px;'>
              DOCUMENTO DE REMESSA
            </td>
          </tr>
        </table>
      </td></tr>
      <tr><td style='padding:30px 32px 16px;font-family:Arial,Helvetica,sans-serif;'>
        <div style='color:#bd111c;font-size:11px;font-weight:bold;letter-spacing:1.4px;'>
          {subject}
        </div>
        <h1 style='margin:10px 0 6px;color:#17233b;font-size:24px;line-height:30px;font-weight:700;'>
          Memorando de Remessa
        </h1>
        <div style='color:#687385;font-size:13px;line-height:20px;'>
          {code} <span style='color:#c2c8d0;'>&nbsp;|&nbsp;</span> Revisão {revision}
        </div>
      </td></tr>
      <tr><td style='padding:8px 32px 26px;font-family:Arial,Helvetica,sans-serif;'>
        <p style='margin:0;color:#4c596c;font-size:14px;line-height:23px;'>
          Olá,<br>
          Encaminhamos o memorando referente às notas fiscais relacionadas à obra abaixo.
          O documento completo está anexado em PDF para consulta e impressão.
        </p>
      </td></tr>
      <tr><td style='padding:0 32px 27px;'>
        <table role='presentation' cellpadding='0' cellspacing='0' width='100%'
               style='border:1px solid #e3e7ef;border-collapse:separate;border-spacing:0;border-radius:8px;'>
          <tr><td style='padding:14px 17px;background:#f7f8fb;border-bottom:1px solid #e3e7ef;'>
            <span style='color:#25334a;font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:bold;'>
              Dados da remessa
            </span>
          </td></tr>
          <tr><td style='padding:4px 17px 7px;'>
            <table role='presentation' cellpadding='0' cellspacing='0' width='100%' style='border-collapse:collapse;'>
              {''.join(fields)}
            </table>
          </td></tr>
        </table>
      </td></tr>
      {notes_html}
      <tr><td style='padding:0 32px 32px;'>
        <table role='presentation' cellpadding='0' cellspacing='0' border='0' width='100%'
               style='background:#fff7f7;border-left:3px solid #bd111c;'>
          <tr><td style='padding:15px 18px;color:#4c596c;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:21px;'>
            <strong style='color:#17233b;'>PDF anexado</strong><br>
            Utilize o arquivo em anexo para imprimir, conferir as notas fiscais e coletar as assinaturas.
          </td></tr>
        </table>
      </td></tr>
      <tr><td style='padding:20px 32px;background:#f7f8fb;border-top:1px solid #e9ecf2;'>
        <div style='font-family:Arial,Helvetica,sans-serif;color:#637083;font-size:11px;line-height:18px;'>
          <strong style='color:#26344a;'>R.S. Daruix Engenharia Ltda.</strong><br>
          Mensagem automática do Daruix Hub. Responda a este e-mail somente se necessário.
        </div>
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>"""


def _attach_inline_logo(email: EmailMultiAlternatives) -> None:
    if not LOGO_PATH.exists():
        return
    try:
        content = LOGO_PATH.read_bytes()
    except OSError:
        return
    image = MIMEImage(content)
    image.add_header("Content-ID", f"<{LOGO_CID}>")
    image.add_header("Content-Disposition", "inline", filename="daruix_logo.png")
    email.attach(image)
    # Django 6: nao utilizar mixed_subtype; o logo e enviado como anexo inline com CID.


def _attach_uploaded_files(
    *,
    email: EmailMultiAlternatives,
    shipment_memo: ShipmentMemo,
    current_total_size: int,
    maximum_total_size: int,
) -> int:
    shipment_files = (
        shipment_memo.files
        .all()
        .order_by(
            "created_at",
            "id",
        )
    )

    total_size = current_total_size

    for shipment_file in shipment_files:
        if not shipment_file.file:
            raise ShipmentMemoEmailError(
                f"O arquivo '{shipment_file.original_name}' "
                "não possui conteúdo físico."
            )

        storage = shipment_file.file.storage
        stored_name = shipment_file.file.name

        if not stored_name or not storage.exists(stored_name):
            raise ShipmentMemoEmailError(
                f"O arquivo '{shipment_file.original_name}' "
                "não foi encontrado no storage."
            )

        try:
            with storage.open(
                stored_name,
                mode="rb",
            ) as file_handle:
                content = file_handle.read()
        except OSError as error:
            raise ShipmentMemoEmailError(
                f"Não foi possível abrir o arquivo "
                f"'{shipment_file.original_name}'."
            ) from error

        total_size += len(content)

        if total_size > maximum_total_size:
            maximum_mb = maximum_total_size / 1024 / 1024
            raise ShipmentMemoEmailError(
                "O tamanho total dos anexos ultrapassa "
                f"o limite de {maximum_mb:.0f} MB."
            )

        email.attach(
            filename=shipment_file.original_name,
            content=content,
            mimetype=(shipment_file.content_type or "application/octet-stream"),
        )

    return total_size


def send_shipment_memo_email(*, shipment_memo: ShipmentMemo) -> None:
    recipients = list(dict.fromkeys(shipment_memo.recipient_emails or []))
    recipient_set = set(recipients)
    cc = [
        email
        for email in dict.fromkeys(shipment_memo.cc_emails or [])
        if email not in recipient_set
    ]

    if not recipients:
        raise ShipmentMemoEmailError("O memorando não possui destinatários.")

    maximum_total_size = int(
        getattr(settings, "SHIPMENT_MEMO_MAX_EMAIL_BYTES", 20 * 1024 * 1024)
    )

    try:
        pdf_content = generate_shipment_memo_pdf(shipment_memo=shipment_memo)
    except ShipmentMemoPdfError as error:
        raise ShipmentMemoEmailError(str(error)) from error

    if len(pdf_content) > maximum_total_size:
        raise ShipmentMemoEmailError(
            "O PDF do memorando ultrapassa o limite permitido para envio."
        )

    email = EmailMultiAlternatives(
        subject=_build_subject(shipment_memo),
        body=_build_text_body(shipment_memo),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
        cc=cc,
    )

    email.attach_alternative(_build_html_body(shipment_memo), "text/html")
    _attach_inline_logo(email)

    email.attach(
        filename=f"{shipment_memo.code}.pdf",
        content=pdf_content,
        mimetype="application/pdf",
    )

    _attach_uploaded_files(
        email=email,
        shipment_memo=shipment_memo,
        current_total_size=len(pdf_content),
        maximum_total_size=maximum_total_size,
    )

    try:
        sent_count = email.send(fail_silently=False)
    except Exception as error:
        logger.exception("Falha ao enviar o memorando %s.", shipment_memo.code)
        raise ShipmentMemoEmailError(
            "O servidor de e-mail recusou ou não concluiu o envio."
        ) from error

    if sent_count != 1:
        raise ShipmentMemoEmailError("O servidor de e-mail não confirmou o envio.")
