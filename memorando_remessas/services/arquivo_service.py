from pathlib import Path

from django.conf import settings
from django.db import transaction
from rest_framework import serializers

from memorando_remessas.models import (
    ShipmentMemo,
    ShipmentMemoFile,
    ShipmentMemoHistoryAction,
)
from memorando_remessas.services.historico_service import (
    register_shipment_memo_history,
)


def _validate_uploaded_file(
    uploaded_file,
) -> None:
    original_name = Path(
        uploaded_file.name
    ).name

    extension = (
        Path(original_name)
        .suffix
        .lower()
    )

    allowed_extensions = {
        extension.lower()
        for extension
        in settings.SHIPMENT_MEMO_ALLOWED_FILE_EXTENSIONS
    }

    if extension not in allowed_extensions:
        raise serializers.ValidationError({
            "file": (
                "Formato de arquivo não permitido. "
                f"Formatos aceitos: "
                f"{', '.join(sorted(allowed_extensions))}."
            )
        })

    max_size_bytes = (
        settings.SHIPMENT_MEMO_MAX_FILE_SIZE_MB
        * 1024
        * 1024
    )

    if uploaded_file.size <= 0:
        raise serializers.ValidationError({
            "file": "O arquivo enviado está vazio."
        })

    if uploaded_file.size > max_size_bytes:
        raise serializers.ValidationError({
            "file": (
                "O arquivo excede o tamanho máximo "
                f"de {settings.SHIPMENT_MEMO_MAX_FILE_SIZE_MB} MB."
            )
        })

    if len(original_name) > 255:
        raise serializers.ValidationError({
            "file": (
                "O nome do arquivo excede "
                "o limite de 255 caracteres."
            )
        })


@transaction.atomic
def add_shipment_memo_file(
    *,
    shipment_memo: ShipmentMemo,
    uploaded_file,
    user,
) -> ShipmentMemoFile:
    shipment_memo = (
        ShipmentMemo.objects
        .select_for_update()
        .get(pk=shipment_memo.pk)
    )

    if not shipment_memo.is_draft:
        raise serializers.ValidationError({
            "detail": (
                "Arquivos somente podem ser adicionados "
                "a memorandos em rascunho."
            )
        })

    _validate_uploaded_file(
        uploaded_file
    )

    current_file_count = (
        shipment_memo.files.count()
    )

    if (
        current_file_count
        >= settings.SHIPMENT_MEMO_MAX_FILES_PER_MEMO
    ):
        raise serializers.ValidationError({
            "file": (
                "O memorando atingiu o limite máximo "
                f"de {settings.SHIPMENT_MEMO_MAX_FILES_PER_MEMO} "
                "arquivos."
            )
        })

    original_name = Path(
        uploaded_file.name
    ).name.strip()

    shipment_file = ShipmentMemoFile(
        shipment_memo=shipment_memo,
        file=uploaded_file,
        original_name=original_name,
        content_type=(
            getattr(
                uploaded_file,
                "content_type",
                "",
            )
            or ""
        ),
        size=uploaded_file.size,
        uploaded_by=user,
    )

    try:
        shipment_file.save()

        register_shipment_memo_history(
            shipment_memo=shipment_memo,
            action=(
                ShipmentMemoHistoryAction.FILE_ADDED
            ),
            actor=user,
            description=(
                f"Arquivo adicionado: {original_name}."
            ),
            metadata={
                "file_id": shipment_file.id,
                "original_name": original_name,
                "content_type": (
                    shipment_file.content_type
                ),
                "size": shipment_file.size,
            },
        )

    except Exception:
        if (
            shipment_file.file
            and shipment_file.file.name
        ):
            storage = shipment_file.file.storage
            file_name = shipment_file.file.name

            if storage.exists(file_name):
                storage.delete(file_name)

        raise

    return shipment_file


@transaction.atomic
def delete_shipment_memo_file(
    *,
    shipment_memo: ShipmentMemo,
    shipment_file: ShipmentMemoFile,
    user,
) -> None:
    shipment_memo = (
        ShipmentMemo.objects
        .select_for_update()
        .get(pk=shipment_memo.pk)
    )

    if not shipment_memo.is_draft:
        raise serializers.ValidationError({
            "detail": (
                "Arquivos somente podem ser removidos "
                "de memorandos em rascunho."
            )
        })

    shipment_file = (
        ShipmentMemoFile.objects
        .select_for_update()
        .filter(
            pk=shipment_file.pk,
            shipment_memo=shipment_memo,
        )
        .first()
    )

    if not shipment_file:
        raise serializers.ValidationError({
            "detail": (
                "O arquivo não pertence ao memorando informado."
            )
        })

    metadata = {
        "file_id": shipment_file.id,
        "original_name": (
            shipment_file.original_name
        ),
        "content_type": (
            shipment_file.content_type
        ),
        "size": shipment_file.size,
    }

    original_name = (
        shipment_file.original_name
    )

    shipment_file.delete()

    register_shipment_memo_history(
        shipment_memo=shipment_memo,
        action=ShipmentMemoHistoryAction.FILE_REMOVED,
        actor=user,
        description=(
            f"Arquivo removido: {original_name}."
        ),
        metadata=metadata,
    )