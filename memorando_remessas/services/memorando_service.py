import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone
from rest_framework import serializers

from accounts.models.choices import UserType
from memorando_remessas.models import (
    ShipmentMemo,
    ShipmentMemoHistoryAction,
    ShipmentMemoOption,
    ShipmentMemoOptionSelection,
    ShipmentMemoResponsible,
    ShipmentMemoStatus,
    WorkSource,
)
from memorando_remessas.permissions import (
    SHIPMENT_MEMO_BE_RESPONSIBLE_PERMISSION,
)
from memorando_remessas.services.codigo_service import (
    generate_shipment_memo_code,
)
from memorando_remessas.services.historico_service import (
    register_shipment_memo_history,
    serialize_shipment_memo_state,
)
from memorando_remessas.services.legacy_service import (
    LegacyBridgeError,
    get_legacy_work,
)
from memorando_remessas.services.memorando_email_service import (
    ShipmentMemoEmailError,
    send_shipment_memo_email,
)


logger = logging.getLogger(__name__)

User = get_user_model()


def _normalize_ids(values) -> set[int]:
    normalized_ids = set()

    for value in values or []:
        try:
            normalized_value = int(value)
        except (TypeError, ValueError):
            continue

        if normalized_value > 0:
            normalized_ids.add(normalized_value)

    return normalized_ids


def _validate_actor(user) -> None:
    if not user or not user.is_authenticated:
        raise serializers.ValidationError({
            "detail": "Usuário não autenticado.",
        })

    if not user.is_active:
        raise serializers.ValidationError({
            "detail": "O usuário está inativo.",
        })

    if user.user_type != UserType.EMPLOYEE:
        raise serializers.ValidationError({
            "detail": (
                "Somente colaboradores podem executar "
                "operações em memorandos de remessa."
            )
        })


def _get_legacy_work_or_error(
    legacy_work_id: int,
) -> dict:
    try:
        work = get_legacy_work(
            legacy_work_id=legacy_work_id,
        )
    except LegacyBridgeError as error:
        raise serializers.ValidationError({
            "legacy_work_id": str(error),
        }) from error

    if not work:
        raise serializers.ValidationError({
            "legacy_work_id": (
                "A obra não foi encontrada ou não está ativa "
                "no sistema legado."
            )
        })

    return work


def _get_responsible_users(
    user_ids,
    current_user,
) -> list:
    normalized_ids = _normalize_ids(user_ids)
    normalized_ids.discard(current_user.id)

    if not normalized_ids:
        return []

    eligibility_filter = (
        Q(is_superuser=True)
        |
        Q(
            group__is_active=True,
            group__group_permissions__is_active=True,
            group__group_permissions__permission__is_active=True,
            group__group_permissions__permission__code=(
                SHIPMENT_MEMO_BE_RESPONSIBLE_PERMISSION
            ),
        )
    )

    users = list(
        User.objects
        .filter(
            id__in=normalized_ids,
            is_active=True,
            user_type=UserType.EMPLOYEE,
        )
        .filter(eligibility_filter)
        .select_related("group")
        .distinct()
    )

    found_ids = {
        user.id
        for user in users
    }

    missing_ids = normalized_ids - found_ids

    if missing_ids:
        raise serializers.ValidationError({
            "responsible_user_ids": (
                "Um ou mais usuários não existem, estão inativos "
                "ou não podem ser responsáveis. "
                f"IDs inválidos: {sorted(missing_ids)}"
            )
        })

    return users


def _get_active_options(option_ids) -> list:
    normalized_ids = _normalize_ids(option_ids)

    if not normalized_ids:
        return []

    options = list(
        ShipmentMemoOption.objects
        .filter(
            id__in=normalized_ids,
            is_active=True,
        )
        .order_by(
            "option_type",
            "order",
            "name",
        )
    )

    found_ids = {
        option.id
        for option in options
    }

    missing_ids = normalized_ids - found_ids

    if missing_ids:
        raise serializers.ValidationError({
            "option_ids": (
                "Uma ou mais opções não existem ou estão inativas. "
                f"IDs inválidos: {sorted(missing_ids)}"
            )
        })

    return options


def _apply_legacy_snapshot(
    shipment_memo: ShipmentMemo,
    work: dict,
) -> None:
    shipment_memo.work_source = WorkSource.ACCESS
    shipment_memo.legacy_work_id = work["legacy_work_id"]
    shipment_memo.legacy_proposal_id = (
        work.get("legacy_proposal_id")
    )
    shipment_memo.cost_center = (
        work.get("cost_center") or ""
    )
    shipment_memo.work_name = (
        work.get("work_name") or ""
    )
    shipment_memo.client_name = (
        work.get("client_name") or ""
    )
    shipment_memo.client_document = (
        work.get("client_document") or ""
    )


def _sync_responsibles(
    shipment_memo: ShipmentMemo,
    responsible_user_ids,
    actor,
) -> None:
    primary_link = (
        shipment_memo.responsible_links
        .filter(is_primary=True)
        .select_related("user")
        .first()
    )

    if not primary_link:
        primary_link = ShipmentMemoResponsible.objects.create(
            shipment_memo=shipment_memo,
            user=actor,
            is_primary=True,
            added_by=actor,
        )

    responsible_users = _get_responsible_users(
        user_ids=responsible_user_ids,
        current_user=primary_link.user,
    )

    desired_user_ids = {
        user.id
        for user in responsible_users
    }

    desired_user_ids.add(
        primary_link.user_id
    )

    shipment_memo.responsible_links.filter(
        is_primary=False,
    ).exclude(
        user_id__in=desired_user_ids,
    ).delete()

    existing_user_ids = set(
        shipment_memo.responsible_links
        .values_list(
            "user_id",
            flat=True,
        )
    )

    for user in responsible_users:
        if user.id in existing_user_ids:
            continue

        ShipmentMemoResponsible.objects.create(
            shipment_memo=shipment_memo,
            user=user,
            is_primary=False,
            added_by=actor,
        )


def _sync_options(
    shipment_memo: ShipmentMemo,
    option_ids,
    actor,
) -> None:
    options = _get_active_options(option_ids)

    desired_option_ids = {
        option.id
        for option in options
    }

    shipment_memo.option_selections.exclude(
        option_id__in=desired_option_ids,
    ).delete()

    existing_option_ids = set(
        shipment_memo.option_selections
        .values_list(
            "option_id",
            flat=True,
        )
    )

    for option in options:
        if option.id in existing_option_ids:
            continue

        ShipmentMemoOptionSelection.objects.create(
            shipment_memo=shipment_memo,
            option=option,
            selected_by=actor,
        )


def _validate_ready_to_send(
    shipment_memo: ShipmentMemo,
) -> None:
    errors = {}

    if not shipment_memo.legacy_work_id:
        errors["legacy_work_id"] = (
            "A obra deve ser informada."
        )

    if not shipment_memo.cost_center.strip():
        errors["cost_center"] = (
            "O centro de custo deve ser informado."
        )

    if not shipment_memo.work_name.strip():
        errors["work_name"] = (
            "O nome da obra deve ser informado."
        )

    if not shipment_memo.client_name.strip():
        errors["client_name"] = (
            "O cliente deve ser informado."
        )

    if not shipment_memo.shipping_date:
        errors["shipping_date"] = (
            "A data da remessa deve ser informada."
        )

    if not shipment_memo.subject.strip():
        errors["subject"] = (
            "O assunto deve ser informado."
        )

    if not shipment_memo.attention_to.strip():
        errors["attention_to"] = (
            "O campo 'Aos cuidados de' deve ser informado."
        )

    if not shipment_memo.recipient_emails:
        errors["recipient_emails"] = (
            "Informe pelo menos um e-mail destinatário."
        )

    primary_responsible_exists = (
        shipment_memo.responsible_links
        .filter(is_primary=True)
        .exists()
    )

    if not primary_responsible_exists:
        errors["responsible_users"] = (
            "O memorando deve possuir um responsável principal."
        )

    if errors:
        raise serializers.ValidationError(errors)

    if shipment_memo.work_source == WorkSource.ACCESS:
        _get_legacy_work_or_error(
            legacy_work_id=shipment_memo.legacy_work_id,
        )


@transaction.atomic
def create_shipment_memo(
    validated_data: dict,
    user,
) -> ShipmentMemo:
    _validate_actor(user)

    responsible_user_ids = validated_data.pop(
        "responsible_user_ids",
        [],
    )

    option_ids = validated_data.pop(
        "option_ids",
        [],
    )

    legacy_work_id = validated_data.pop(
        "legacy_work_id",
    )

    work = _get_legacy_work_or_error(
        legacy_work_id=legacy_work_id,
    )

    responsible_users = _get_responsible_users(
        user_ids=responsible_user_ids,
        current_user=user,
    )

    options = _get_active_options(
        option_ids=option_ids,
    )

    sequence_number, code = (
        generate_shipment_memo_code()
    )

    shipment_memo = ShipmentMemo(
        code=code,
        sequence_number=sequence_number,
        revision=1,
        created_by=user,
        updated_by=user,
        **validated_data,
    )

    _apply_legacy_snapshot(
        shipment_memo=shipment_memo,
        work=work,
    )

    shipment_memo.save()

    ShipmentMemoResponsible.objects.create(
        shipment_memo=shipment_memo,
        user=user,
        is_primary=True,
        added_by=user,
    )

    for responsible_user in responsible_users:
        ShipmentMemoResponsible.objects.create(
            shipment_memo=shipment_memo,
            user=responsible_user,
            is_primary=False,
            added_by=user,
        )

    for option in options:
        ShipmentMemoOptionSelection.objects.create(
            shipment_memo=shipment_memo,
            option=option,
            selected_by=user,
        )

    register_shipment_memo_history(
        shipment_memo=shipment_memo,
        action=ShipmentMemoHistoryAction.CREATED,
        actor=user,
        description="Memorando de remessa criado.",
        after_data=serialize_shipment_memo_state(
            shipment_memo
        ),
    )

    return shipment_memo


@transaction.atomic
def update_shipment_memo(
    shipment_memo: ShipmentMemo,
    validated_data: dict,
    user,
) -> ShipmentMemo:
    _validate_actor(user)

    shipment_memo = (
        ShipmentMemo.objects
        .select_for_update()
        .get(pk=shipment_memo.pk)
    )

    if not shipment_memo.is_editable:
        raise serializers.ValidationError({
            "detail": (
                "Somente memorandos em rascunho "
                "podem ser alterados."
            )
        })

    before_data = serialize_shipment_memo_state(
        shipment_memo
    )

    responsible_ids_were_sent = (
        "responsible_user_ids" in validated_data
    )

    options_were_sent = (
        "option_ids" in validated_data
    )

    responsible_user_ids = validated_data.pop(
        "responsible_user_ids",
        [],
    )

    option_ids = validated_data.pop(
        "option_ids",
        [],
    )

    legacy_work_id = validated_data.pop(
        "legacy_work_id",
        None,
    )

    if legacy_work_id is not None:
        work = _get_legacy_work_or_error(
            legacy_work_id=legacy_work_id,
        )

        _apply_legacy_snapshot(
            shipment_memo=shipment_memo,
            work=work,
        )

    for field, value in validated_data.items():
        setattr(
            shipment_memo,
            field,
            value,
        )

    shipment_memo.subject = (
        shipment_memo.subject.strip()
    )
    shipment_memo.attention_to = (
        shipment_memo.attention_to.strip()
    )
    shipment_memo.notes = (
        shipment_memo.notes.strip()
    )

    shipment_memo.updated_by = user
    shipment_memo.save()

    if responsible_ids_were_sent:
        _sync_responsibles(
            shipment_memo=shipment_memo,
            responsible_user_ids=responsible_user_ids,
            actor=user,
        )

    if options_were_sent:
        _sync_options(
            shipment_memo=shipment_memo,
            option_ids=option_ids,
            actor=user,
        )

    after_data = serialize_shipment_memo_state(
        shipment_memo
    )

    if before_data != after_data:
        register_shipment_memo_history(
            shipment_memo=shipment_memo,
            action=ShipmentMemoHistoryAction.UPDATED,
            actor=user,
            description="Memorando de remessa alterado.",
            before_data=before_data,
            after_data=after_data,
        )

    return shipment_memo


@transaction.atomic
def delete_shipment_memo(
    shipment_memo: ShipmentMemo,
) -> None:
    shipment_memo = (
        ShipmentMemo.objects
        .select_for_update()
        .get(pk=shipment_memo.pk)
    )

    if not shipment_memo.is_draft:
        raise serializers.ValidationError({
            "detail": (
                "Somente memorandos em rascunho "
                "podem ser excluídos."
            )
        })

    if shipment_memo.generated_revisions.exists():
        raise serializers.ValidationError({
            "detail": (
                "O memorando não pode ser excluído porque "
                "possui revisões vinculadas."
            )
        })

    shipment_memo.delete()


def send_shipment_memo(
    shipment_memo: ShipmentMemo,
    user,
) -> ShipmentMemo:
    _validate_actor(user)

    allowed_statuses = {
        ShipmentMemoStatus.DRAFT,
        ShipmentMemoStatus.FAILED,
    }

    with transaction.atomic():
        shipment_memo = (
            ShipmentMemo.objects
            .select_for_update()
            .get(pk=shipment_memo.pk)
        )

        if shipment_memo.status not in allowed_statuses:
            raise serializers.ValidationError({
                "detail": (
                    "Somente memorandos em rascunho ou com "
                    "falha no envio podem ser enviados."
                )
            })

        _validate_ready_to_send(
            shipment_memo
        )

        before_data = serialize_shipment_memo_state(
            shipment_memo
        )

        shipment_memo.status = (
            ShipmentMemoStatus.PROCESSING
        )
        shipment_memo.sent_by = None
        shipment_memo.sent_at = None
        shipment_memo.last_send_error = ""
        shipment_memo.updated_by = user

        shipment_memo.save(
            update_fields=[
                "status",
                "sent_by",
                "sent_at",
                "last_send_error",
                "updated_by",
                "updated_at",
            ]
        )

    try:
        send_shipment_memo_email(
            shipment_memo=shipment_memo,
        )

    except Exception as error:
        logger.exception(
            "Falha no envio do memorando %s.",
            shipment_memo.code,
        )

        error_message = (
            str(error)
            if isinstance(
                error,
                ShipmentMemoEmailError,
            )
            else (
                "Ocorreu uma falha inesperada durante "
                "o envio do memorando."
            )
        )

        with transaction.atomic():
            failed_memo = (
                ShipmentMemo.objects
                .select_for_update()
                .get(pk=shipment_memo.pk)
            )

            if (
                failed_memo.status
                == ShipmentMemoStatus.PROCESSING
            ):
                failed_memo.status = (
                    ShipmentMemoStatus.FAILED
                )
                failed_memo.last_send_error = (
                    error_message[:5000]
                )
                failed_memo.updated_by = user

                failed_memo.save(
                    update_fields=[
                        "status",
                        "last_send_error",
                        "updated_by",
                        "updated_at",
                    ]
                )

        raise serializers.ValidationError({
            "detail": (
                "Não foi possível enviar o memorando por e-mail."
            ),
            "send_error": error_message,
            "status": ShipmentMemoStatus.FAILED,
        }) from error

    with transaction.atomic():
        sent_memo = (
            ShipmentMemo.objects
            .select_for_update()
            .get(pk=shipment_memo.pk)
        )

        if (
            sent_memo.status
            != ShipmentMemoStatus.PROCESSING
        ):
            raise serializers.ValidationError({
                "detail": (
                    "O status do memorando foi alterado enquanto "
                    "o envio estava sendo processado."
                )
            })

        sent_memo.status = ShipmentMemoStatus.SENT
        sent_memo.sent_by = user
        sent_memo.sent_at = timezone.now()
        sent_memo.last_send_error = ""
        sent_memo.updated_by = user

        sent_memo.save(
            update_fields=[
                "status",
                "sent_by",
                "sent_at",
                "last_send_error",
                "updated_by",
                "updated_at",
            ]
        )

    try:
        register_shipment_memo_history(
            shipment_memo=sent_memo,
            action=ShipmentMemoHistoryAction.SENT,
            actor=user,
            description=(
                "Memorando de remessa enviado por e-mail."
            ),
            before_data=before_data,
            after_data=serialize_shipment_memo_state(
                sent_memo
            ),
            metadata={
                "recipient_emails": (
                    sent_memo.recipient_emails
                ),
                "cc_emails": sent_memo.cc_emails,
                "file_count": sent_memo.files.count(),
                "pdf_filename": (
                    f"{sent_memo.code}.pdf"
                ),
            },
        )
    except Exception:
        logger.exception(
            "O memorando %s foi enviado, mas o histórico "
            "do envio não pôde ser registrado.",
            sent_memo.code,
        )

    return sent_memo


@transaction.atomic
def cancel_shipment_memo(
    shipment_memo: ShipmentMemo,
    user,
    reason: str,
) -> ShipmentMemo:
    _validate_actor(user)

    shipment_memo = (
        ShipmentMemo.objects
        .select_for_update()
        .get(pk=shipment_memo.pk)
    )

    if not shipment_memo.is_sent:
        raise serializers.ValidationError({
            "detail": (
                "Somente memorandos enviados "
                "podem ser cancelados."
            )
        })

    reason = str(reason or "").strip()

    if not reason:
        raise serializers.ValidationError({
            "reason": (
                "O motivo do cancelamento deve ser informado."
            )
        })

    before_data = serialize_shipment_memo_state(
        shipment_memo
    )

    shipment_memo.status = ShipmentMemoStatus.CANCELLED
    shipment_memo.cancelled_by = user
    shipment_memo.cancelled_at = timezone.now()
    shipment_memo.cancellation_reason = reason
    shipment_memo.updated_by = user
    shipment_memo.save()

    register_shipment_memo_history(
        shipment_memo=shipment_memo,
        action=ShipmentMemoHistoryAction.CANCELLED,
        actor=user,
        description="Memorando de remessa cancelado.",
        before_data=before_data,
        after_data=serialize_shipment_memo_state(
            shipment_memo
        ),
        metadata={
            "reason": reason,
        },
    )

    return shipment_memo


@transaction.atomic
def create_shipment_memo_revision(
    shipment_memo: ShipmentMemo,
    user,
) -> ShipmentMemo:
    _validate_actor(user)

    source = (
        ShipmentMemo.objects
        .select_for_update()
        .get(pk=shipment_memo.pk)
    )

    if source.status not in [
        ShipmentMemoStatus.SENT,
        ShipmentMemoStatus.CANCELLED,
    ]:
        raise serializers.ValidationError({
            "detail": (
                "Uma nova revisão somente pode ser criada "
                "a partir de um memorando enviado ou cancelado."
            )
        })

    revisions = (
        ShipmentMemo.objects
        .select_for_update()
        .filter(
            sequence_number=source.sequence_number,
        )
    )

    latest_revision = (
        revisions.aggregate(
            maximum=Max("revision"),
        )["maximum"]
        or source.revision
    )

    if source.revision != latest_revision:
        raise serializers.ValidationError({
            "detail": (
                "A nova revisão deve ser criada a partir "
                "da revisão mais recente."
            )
        })

    next_revision = latest_revision + 1

    code = (
        f"MRO{source.sequence_number:05d}"
        f"-{next_revision:02d}"
    )

    new_memo = ShipmentMemo.objects.create(
        code=code,
        sequence_number=source.sequence_number,
        revision=next_revision,
        revised_from=source,
        status=ShipmentMemoStatus.DRAFT,
        work_source=source.work_source,
        legacy_work_id=source.legacy_work_id,
        legacy_proposal_id=source.legacy_proposal_id,
        cost_center=source.cost_center,
        work_name=source.work_name,
        client_name=source.client_name,
        client_document=source.client_document,
        shipping_date=source.shipping_date,
        subject=source.subject,
        attention_to=source.attention_to,
        recipient_emails=list(
            source.recipient_emails
            or []
        ),
        cc_emails=list(
            source.cc_emails
            or []
        ),
        notes=source.notes,
        last_send_error="",
        created_by=user,
        updated_by=user,
    )

    source_responsibles = list(
        source.responsible_links
        .select_related("user")
        .order_by(
            "-is_primary",
            "created_at",
        )
    )

    primary_created = False

    for link in source_responsibles:
        responsible_user = link.user

        if not responsible_user.is_active:
            continue

        if responsible_user.user_type != UserType.EMPLOYEE:
            continue

        is_primary = (
            link.is_primary
            and not primary_created
        )

        ShipmentMemoResponsible.objects.create(
            shipment_memo=new_memo,
            user=responsible_user,
            is_primary=is_primary,
            added_by=user,
        )

        if is_primary:
            primary_created = True

    if not primary_created:
        actor_link = (
            new_memo.responsible_links
            .filter(user=user)
            .first()
        )

        if actor_link:
            actor_link.is_primary = True
            actor_link.save(
                update_fields=[
                    "is_primary",
                ]
            )
        else:
            ShipmentMemoResponsible.objects.create(
                shipment_memo=new_memo,
                user=user,
                is_primary=True,
                added_by=user,
            )

    source_options = list(
        source.option_selections
        .select_related("option")
        .all()
    )

    for selection in source_options:
        ShipmentMemoOptionSelection.objects.create(
            shipment_memo=new_memo,
            option=selection.option,
            selected_by=user,
        )

    register_shipment_memo_history(
        shipment_memo=source,
        action=ShipmentMemoHistoryAction.REVISION_CREATED,
        actor=user,
        description=(
            f"Nova revisão criada: {new_memo.code}."
        ),
        metadata={
            "new_revision_id": new_memo.id,
            "new_revision_code": new_memo.code,
        },
    )

    register_shipment_memo_history(
        shipment_memo=new_memo,
        action=ShipmentMemoHistoryAction.REVISION_CREATED,
        actor=user,
        description=(
            f"Revisão criada a partir de {source.code}."
        ),
        after_data=serialize_shipment_memo_state(
            new_memo
        ),
        metadata={
            "source_id": source.id,
            "source_code": source.code,
        },
    )

    return new_memo
