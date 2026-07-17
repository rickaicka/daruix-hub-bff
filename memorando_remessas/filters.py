from django_filters import rest_framework as filters

from memorando_remessas.models import (
    ShipmentMemo,
    ShipmentMemoStatus,
    WorkSource,
)


class ShipmentMemoFilter(filters.FilterSet):
    status = filters.MultipleChoiceFilter(
        choices=ShipmentMemoStatus.choices,
    )

    work_source = filters.MultipleChoiceFilter(
        choices=WorkSource.choices,
    )

    shipping_date_from = filters.DateFilter(
        field_name="shipping_date",
        lookup_expr="gte",
    )

    shipping_date_to = filters.DateFilter(
        field_name="shipping_date",
        lookup_expr="lte",
    )

    created_at_from = filters.IsoDateTimeFilter(
        field_name="created_at",
        lookup_expr="gte",
    )

    created_at_to = filters.IsoDateTimeFilter(
        field_name="created_at",
        lookup_expr="lte",
    )

    responsible_user_id = filters.NumberFilter(
        field_name="responsible_links__user_id",
    )

    legacy_work_id = filters.NumberFilter(
        field_name="legacy_work_id",
    )

    class Meta:
        model = ShipmentMemo

        fields = [
            "status",
            "work_source",
            "legacy_work_id",
            "created_by",
            "responsible_user_id",
        ]