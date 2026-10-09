from django.db.models import Prefetch, QuerySet

from .models import (
    ServiceComposition,
    ServiceCompositionItem,
    ServiceCompositionVersion,
    Supply,
)


def supply_queryset() -> QuerySet[Supply]:
    """Consulta-base dos insumos com os relacionamentos usados pela API."""

    return Supply.objects.select_related(
        "unit_measure",
        "material_group",
        "created_by",
        "updated_by",
    )


def service_composition_queryset() -> QuerySet[ServiceComposition]:
    """Carrega somente a versão mais recente e seus itens.

    O ``to_attr`` também permite que ``ServiceComposition.latest_version``
    reutilize o prefetch sem executar uma consulta por composição.
    """

    items = ServiceCompositionItem.objects.select_related(
        "supply",
        "subcomposition",
    ).order_by("position", "id")

    latest_version = ServiceCompositionVersion.objects.order_by(
        "-number"
    ).prefetch_related(
        Prefetch(
            "items",
            queryset=items,
        )
    )[:1]

    return ServiceComposition.objects.prefetch_related(
        Prefetch(
            "versions",
            queryset=latest_version,
            to_attr="_prefetched_latest_versions",
        )
    )
