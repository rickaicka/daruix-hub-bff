import re

from django.db import transaction

from memorando_remessas.models import ShipmentMemoSequence


SHIPMENT_MEMO_SEQUENCE_KEY_PREFIX = "shipment_memo:pc"

_PC_NUMBER_PATTERN = re.compile(
    r"(?:PC\s*[-./]?\s*)?(\d+)",
    flags=re.IGNORECASE,
)


class ShipmentMemoCodeError(ValueError):
    """Erro ao extrair o PC ou gerar o código do memorando."""


def extract_pc_number(
    cost_center: str,
) -> str:
    normalized_cost_center = str(
        cost_center or ""
    ).strip()

    if not normalized_cost_center:
        raise ShipmentMemoCodeError(
            "O centro de custo da obra não foi informado."
        )

    match = _PC_NUMBER_PATTERN.search(
        normalized_cost_center
    )

    if not match:
        raise ShipmentMemoCodeError(
            "Não foi possível identificar o número do PC "
            f"no centro de custo '{normalized_cost_center}'."
        )

    raw_pc_number = match.group(1)

    try:
        pc_number = str(int(raw_pc_number))
    except (TypeError, ValueError) as error:
        raise ShipmentMemoCodeError(
            "O número do PC informado é inválido."
        ) from error

    if not pc_number or pc_number == "0":
        raise ShipmentMemoCodeError(
            "O número do PC deve ser maior que zero."
        )

    return pc_number


def build_shipment_memo_sequence_key(
    *,
    pc_number: str,
) -> str:
    return (
        f"{SHIPMENT_MEMO_SEQUENCE_KEY_PREFIX}:"
        f"{pc_number}"
    )


@transaction.atomic
def generate_shipment_memo_code(
    *,
    cost_center: str,
) -> tuple[int, str]:
    pc_number = extract_pc_number(
        cost_center
    )

    sequence_key = (
        build_shipment_memo_sequence_key(
            pc_number=pc_number,
        )
    )

    sequence, _ = (
        ShipmentMemoSequence.objects
        .select_for_update()
        .get_or_create(
            key=sequence_key,
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

    code = (
        f"MR{pc_number}"
        f"-{sequence_number:03d}"
    )

    return sequence_number, code