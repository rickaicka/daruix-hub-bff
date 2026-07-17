from django.db import transaction

from memorando_remessas.models import ShipmentMemoSequence


SHIPMENT_MEMO_SEQUENCE_KEY = "shipment_memo"


@transaction.atomic
def generate_shipment_memo_code() -> tuple[int, str]:
    sequence, _ = (
        ShipmentMemoSequence.objects
        .select_for_update()
        .get_or_create(
            key=SHIPMENT_MEMO_SEQUENCE_KEY,
            defaults={
                "current_value": 0,
            },
        )
    )

    sequence.current_value += 1
    sequence.save(
        update_fields=[
            "current_value",
            "updated_at",
        ]
    )

    sequence_number = sequence.current_value
    revision = 1

    code = (
        f"MRO{sequence_number:05d}"
        f"-{revision:02d}"
    )

    return sequence_number, code