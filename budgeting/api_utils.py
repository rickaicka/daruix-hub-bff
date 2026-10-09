from typing import NoReturn

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError


def raise_api_validation_error(error: DjangoValidationError) -> NoReturn:
    """Converte um erro de domínio do Django para o contrato do DRF."""

    detail = getattr(error, "message_dict", error.messages)
    raise ValidationError(detail) from error
