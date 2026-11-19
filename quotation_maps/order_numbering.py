"""Numeração OC + 5 dígitos da PC + sequência de 3 dígitos.

IMPORTANTE: a sequência é global por PC entre legado e Hub. Sem um
marco legado confiável, a emissão falha para impedir duplicação.
"""
import json
import os
from django.conf import settings


def make_order_code(pc_code: str, sequence: int) -> str:
    if len(pc_code) != 7 or not pc_code.startswith('PC') or not pc_code[2:].isdigit():
        raise ValueError('A PC deve estar no formato PC26031 (5 dígitos).')
    if not 1 <= sequence <= 999:
        raise ValueError('A sequência de OC deve estar entre 001 e 999.')
    return f'OC{pc_code[2:]}{sequence:03d}'


def legacy_last_sequence(pc_code: str) -> int:
    """Resolve marco legado via Bridge; override explícito somente para exceções.

    O Bridge indisponível ou a resposta ambígua nunca deve produzir zero.
    """
    if len(pc_code) != 7 or not pc_code.startswith("PC") or not pc_code[2:].isdigit():
        raise ValueError("PC inválida para conciliação de OC.")
    mapping = getattr(settings, "OC_LEGACY_LAST_BY_PC", None)
    if mapping is None:
        mapping = os.environ.get("OC_LEGACY_LAST_BY_PC", "{}")
    if isinstance(mapping, str):
        try:
            mapping = json.loads(mapping)
        except json.JSONDecodeError as error:
            raise ValueError("Configuração OC_LEGACY_LAST_BY_PC inválida.") from error
    if not isinstance(mapping, dict):
        raise ValueError("Configuração OC_LEGACY_LAST_BY_PC inválida.")
    if pc_code in mapping:
        try:
            n = int(mapping[pc_code])
        except (ValueError, TypeError) as error:
            raise ValueError(f"Última sequência legada inválida para {pc_code}.") from error
        if not 0 <= n <= 999:
            raise ValueError(f"Última sequência legada inválida para {pc_code}.")
        return n

    from integrations.legacy_bridge.client import LegacyBridgeClient, LegacyBridgeHttpError
    try:
        result = LegacyBridgeClient().last_purchase_order_sequence(pc_code)
    except LegacyBridgeHttpError as error:
        raise ValueError(
            f"Não foi possível conciliar as OCs da {pc_code} via Legacy Bridge: {error}"
        ) from error
    if result.get("pc") != pc_code or result.get("source") != "tblOrdemDeCompra":
        raise ValueError(f"Resposta de conciliação inválida para {pc_code}.")
    if not isinstance(result.get("found"), bool):
        raise ValueError(f"Resposta de conciliação inválida para {pc_code}.")
    raw_count = result.get("matched_orders")
    raw_sequence = result.get("last_suffix")
    if type(raw_count) is not int or type(raw_sequence) is not int:
        raise ValueError(f"Resposta de conciliação inválida para {pc_code}.")
    if raw_count < 0 or not 0 <= raw_sequence <= 999:
        raise ValueError(f"Resposta de conciliação inválida para {pc_code}.")
    if result["found"] != (raw_count > 0) or (raw_count == 0 and raw_sequence != 0):
        raise ValueError(f"Resposta de conciliação inconsistente para {pc_code}.")
    return raw_sequence
