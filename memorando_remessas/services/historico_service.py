from datetime import date, datetime
from decimal import Decimal
from typing import Any

from memorando_remessas.models import (
    ShipmentMemo,
    ShipmentMemoHistory,
)


def _serialize_value(value: Any):
    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return str(value)

    return value


def serialize_shipment_memo_state(
    shipment_memo: ShipmentMemo,
) -> dict:
    responsible_user_ids = list(
        shipment_memo.responsible_links
        .order_by(
            "-is_primary",
            "user_id",
        )
        .values_list(
            "user_id",
            flat=True,
        )
    )

    option_ids = list(
        shipment_memo.option_selections
        .order_by("option_id")
        .values_list(
            "option_id",
            flat=True,
        )
    )

    state = {
        "id": shipment_memo.id,
        "code": shipment_memo.code,
        "sequence_number": shipment_memo.sequence_number,
        "revision": shipment_memo.revision,
        "revised_from_id": shipment_memo.revised_from_id,
        "status": shipment_memo.status,
        "work_source": shipment_memo.work_source,
        "legacy_work_id": shipment_memo.legacy_work_id,
        "legacy_proposal_id": shipment_memo.legacy_proposal_id,
        "cost_center": shipment_memo.cost_center,
        "work_name": shipment_memo.work_name,
        "client_name": shipment_memo.client_name,
        "client_document": shipment_memo.client_document,
        "shipping_date": shipment_memo.shipping_date,
        "subject": shipment_memo.subject,
        "attention_to": shipment_memo.attention_to,
        "notes": shipment_memo.notes,
        "created_by_id": shipment_memo.created_by_id,
        "updated_by_id": shipment_memo.updated_by_id,
        "sent_by_id": shipment_memo.sent_by_id,
        "sent_at": shipment_memo.sent_at,
        "cancelled_by_id": shipment_memo.cancelled_by_id,
        "cancelled_at": shipment_memo.cancelled_at,
        "cancellation_reason": (
            shipment_memo.cancellation_reason
        ),
        "responsible_user_ids": responsible_user_ids,
        "option_ids": option_ids,
    }

    return {
        key: _serialize_value(value)
        for key, value in state.items()
    }


def register_shipment_memo_history(
    *,
    shipment_memo: ShipmentMemo,
    action: str,
    actor,
    description: str = "",
    before_data: dict | None = None,
    after_data: dict | None = None,
    metadata: dict | None = None,
) -> ShipmentMemoHistory:
    return ShipmentMemoHistory.objects.create(
        shipment_memo=shipment_memo,
        action=action,
        actor=actor,
        description=str(description or "").strip(),
        before_data=before_data or {},
        after_data=after_data or {},
        metadata=metadata or {},
    )