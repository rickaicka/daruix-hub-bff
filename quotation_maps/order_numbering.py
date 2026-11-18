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
    """Marco obtido de TODAS as OCs legadas, inclusive encerradas.

    Defina OC_LEGACY_LAST_BY_PC no settings (dict) ou, se integrado ao
    settings, parse de variável segura no lado servidor. Valores faltantes
    devem impedir geração até reconciliação da sequência.
    """
    mapping = getattr(settings, 'OC_LEGACY_LAST_BY_PC', None)
    if mapping is None:
        mapping = os.environ.get('OC_LEGACY_LAST_BY_PC', '{}')
    if isinstance(mapping, str):
        mapping = json.loads(mapping)
    if pc_code not in mapping:
        raise ValueError(f'Sequência legada da {pc_code} não conciliada. Cadastre o último sufixo (0 se não existir).')
    n = int(mapping[pc_code])
    if not 0 <= n <= 999:
        raise ValueError(f'Última sequência legada inválida para {pc_code}.')
    return n
