"""Validação e aplicação de desconto sobre um preço unitário já formado."""
from decimal import Decimal

from django.core.exceptions import ValidationError


def discounted_unit_price(gross_price, discount=Decimal("0")):
    """Subtrai o desconto sem introduzir um novo arredondamento.

    A formação do preço bruto pertence ao chamador: sem BDI ele pode manter a
    precisão do custo; com BDI a regra do XLS entrega aqui o preço de venda já
    arredondado para centavos (ARRED(custo x fator; 2)).
    """
    cent = Decimal("0.01")
    gross = Decimal(gross_price or 0)
    discount = Decimal(discount or 0)

    if not gross.is_finite() or gross < 0:
        raise ValidationError({"unit_price": "Informe um preço unitário válido."})

    if (
        not discount.is_finite()
        or discount < 0
        or discount != discount.quantize(cent)
        or discount > gross
    ):
        raise ValidationError(
            {
                "unit_discount": (
                    "Informe um desconto com até 2 casas, entre zero e o "
                    "preço unitário com BDI."
                )
            }
        )

    return gross - discount
