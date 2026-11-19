"""Prazo de entrega da OC contado a partir de sua criação (data local Django).

Feriados nacionais brasileiros, inclusive Sexta-Feira Santa, e datas extras
configuráveis por município/estado/empresa em QUOTATION_DELIVERY_EXTRA_HOLIDAYS.
Não considera Carnaval/Corpus Christi como nacionais automaticamente.
"""
import re
from datetime import date, timedelta
from functools import lru_cache
from django.conf import settings

_PATTERN = re.compile(r"^([1-9]\d{0,3})\s+dias?\s+(úteis|uteis|corridos)$", re.IGNORECASE)


def parse_delivery_terms(value):
    match = _PATTERN.fullmatch(str(value or "").strip())
    if not match:
        return None
    return int(match[1]), ("BUSINESS" if match[2].lower() in ("úteis", "uteis") else "CALENDAR")


@lru_cache(maxsize=128)
def easter(year):
    # Algoritmo gregoriano de Meeus/Jones/Butcher.
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


@lru_cache(maxsize=128)
def national_holidays(year):
    # Feriados nacionais (incluindo 20 de novembro, Lei 14.759/2023)
    fixed = ((1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2),
             (11, 15), (11, 20), (12, 25))
    return {date(year, month, day) for month, day in fixed} | {easter(year) - timedelta(days=2)}


def _extra_holidays():
    result = set()
    for value in getattr(settings, "QUOTATION_DELIVERY_EXTRA_HOLIDAYS", ()):
        if isinstance(value, date):
            result.add(value)
        elif isinstance(value, str):
            result.add(date.fromisoformat(value))
        else:
            raise ValueError("Feriado adicional deve ser data ISO (YYYY-MM-DD).")
    return result


def expected_delivery_date(creation_date, days, day_type):
    if not isinstance(creation_date, date) or isinstance(creation_date, __import__('datetime').datetime):
        raise ValueError("Informe a data de criação da OC.")
    if not isinstance(days, int) or not 1 <= days <= 9999:
        raise ValueError("Prazo de entrega fora do limite (1–9999 dias).")
    if day_type not in ("BUSINESS", "CALENDAR"):
        raise ValueError("Tipo de prazo inválido.")
    if day_type == "CALENDAR":
        return creation_date + timedelta(days=days)
    extras = _extra_holidays()
    current = creation_date
    remaining = days
    while remaining:
        current += timedelta(days=1)
        if current.weekday() < 5 and current not in national_holidays(current.year) and current not in extras:
            remaining -= 1
    return current
