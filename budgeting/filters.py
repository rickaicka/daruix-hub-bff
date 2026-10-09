import django_filters

from .models import Supply


class SupplyAutocompleteFilter(django_filters.FilterSet):
    class Meta:
        model = Supply
        fields = (
            "origin",
            "supply_type",
            "unit",
            "unit_measure",
            "material_group",
        )