from html import escape
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from memorando_remessas.models import ShipmentMemo
from memorando_remessas.services.memorando_pdf_service import (
    ShipmentMemoPdfError,
    generate_shipment_memo_pdf,
)


logger = logging.getLogger(__name__)


class ShipmentMemoEmailError(Exception):
    """Erro ao montar ou enviar o memorando por e-mail."""


def _format_date(value) -> str:
    if not value:
        return "-"

    return value.strftime("%d/%m/%Y")


def _build_subject(
    shipment_memo: ShipmentMemo,
) -> str:
    return (
        f"{shipment_memo.code} - "
        f"{shipment_memo.subject}"
    )


def _build_text_body(
    shipment_memo: ShipmentMemo,
) -> str:
    return (
        f"Segue o Memorando de Remessa "
        f"{shipment_memo.code}.\n\n"
        f"Revisão: {shipment_memo.revision}\n"
        f"Centro de custo: {shipment_memo.cost_center}\n"
        f"Obra: {shipment_memo.work_name}\n"
        f"Cliente: {shipment_memo.client_name}\n"
        f"Aos cuidados de: {shipment_memo.attention_to}\n"
        f"Data da remessa: "
        f"{_format_date(shipment_memo.shipping_date)}\n"
        f"Assunto: {shipment_memo.subject}\n\n"
        f"Observações:\n"
        f"{shipment_memo.notes or 'Sem observações.'}\n\n"
        f"O memorando em PDF e os documentos enviados "
        f"estão anexados a esta mensagem."
    )


def _build_html_body(
    shipment_memo: ShipmentMemo,
) -> str:
    notes = escape(
        shipment_memo.notes
        or "Sem observações."
    ).replace("\n", "<br>")

    return f"""
    <div style="
        font-family: Arial, sans-serif;
        color: #172033;
        line-height: 1.5;
    ">
        <h2 style="margin-bottom: 4px;">
            Memorando de Remessa
        </h2>

        <p style="margin-top: 0; color: #586174;">
            {escape(shipment_memo.code or "")}
            — Revisão {shipment_memo.revision}
        </p>

        <table style="
            width: 100%;
            max-width: 720px;
            border-collapse: collapse;
        ">
            <tbody>
                <tr>
                    <td style="padding: 6px 10px;">
                        <strong>Centro de custo</strong>
                    </td>
                    <td style="padding: 6px 10px;">
                        {escape(shipment_memo.cost_center)}
                    </td>
                </tr>
                <tr>
                    <td style="padding: 6px 10px;">
                        <strong>Obra</strong>
                    </td>
                    <td style="padding: 6px 10px;">
                        {escape(shipment_memo.work_name)}
                    </td>
                </tr>
                <tr>
                    <td style="padding: 6px 10px;">
                        <strong>Cliente</strong>
                    </td>
                    <td style="padding: 6px 10px;">
                        {escape(shipment_memo.client_name)}
                    </td>
                </tr>
                <tr>
                    <td style="padding: 6px 10px;">
                        <strong>Aos cuidados de</strong>
                    </td>
                    <td style="padding: 6px 10px;">
                        {escape(shipment_memo.attention_to)}
                    </td>
                </tr>
                <tr>
                    <td style="padding: 6px 10px;">
                        <strong>Data da remessa</strong>
                    </td>
                    <td style="padding: 6px 10px;">
                        {_format_date(shipment_memo.shipping_date)}
                    </td>
                </tr>
                <tr>
                    <td style="padding: 6px 10px;">
                        <strong>Assunto</strong>
                    </td>
                    <td style="padding: 6px 10px;">
                        {escape(shipment_memo.subject)}
                    </td>
                </tr>
            </tbody>
        </table>

        <h3>Observações</h3>
        <p>{notes}</p>

        <p>
            O memorando em PDF e os documentos enviados
            estão anexados a esta mensagem.
        </p>
    </div>
    """


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
            maximum_mb = (
                maximum_total_size
                / 1024
                / 1024
            )

            raise ShipmentMemoEmailError(
                "O tamanho total dos anexos ultrapassa "
                f"o limite de {maximum_mb:.0f} MB."
            )

        email.attach(
            filename=shipment_file.original_name,
            content=content,
            mimetype=(
                shipment_file.content_type
                or "application/octet-stream"
            ),
        )

    return total_size


def send_shipment_memo_email(
    *,
    shipment_memo: ShipmentMemo,
) -> None:
    recipients = list(
        dict.fromkeys(
            shipment_memo.recipient_emails
            or []
        )
    )

    recipient_set = set(recipients)

    cc = [
        email
        for email in dict.fromkeys(
            shipment_memo.cc_emails
            or []
        )
        if email not in recipient_set
    ]

    if not recipients:
        raise ShipmentMemoEmailError(
            "O memorando não possui destinatários."
        )

    maximum_total_size = int(
        getattr(
            settings,
            "SHIPMENT_MEMO_MAX_EMAIL_BYTES",
            20 * 1024 * 1024,
        )
    )

    try:
        pdf_content = generate_shipment_memo_pdf(
            shipment_memo=shipment_memo,
        )
    except ShipmentMemoPdfError as error:
        raise ShipmentMemoEmailError(
            str(error)
        ) from error

    if len(pdf_content) > maximum_total_size:
        raise ShipmentMemoEmailError(
            "O PDF do memorando ultrapassa o limite "
            "permitido para envio."
        )

    email = EmailMultiAlternatives(
        subject=_build_subject(shipment_memo),
        body=_build_text_body(shipment_memo),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
        cc=cc,
    )

    email.attach_alternative(
        _build_html_body(shipment_memo),
        "text/html",
    )

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
        sent_count = email.send(
            fail_silently=False,
        )
    except Exception as error:
        logger.exception(
            "Falha ao enviar o memorando %s.",
            shipment_memo.code,
        )

        raise ShipmentMemoEmailError(
            "O servidor de e-mail recusou ou não concluiu o envio."
        ) from error

    if sent_count != 1:
        raise ShipmentMemoEmailError(
            "O servidor de e-mail não confirmou o envio."
        )
