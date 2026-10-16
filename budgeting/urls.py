from rest_framework.routers import DefaultRouter

from .views import (
    BudgetSheetViewSet,
    BudgetStageCatalogViewSet,
    MaterialGroupViewSet,
    ServiceCompositionGroupViewSet,
    ServiceCompositionViewSet,
    SupplyTypeViewSet,
    SupplyViewSet,
    UnitMeasureViewSet,
)

app_name = "budgeting"

router = DefaultRouter()
router.register(
    "stages",
    BudgetStageCatalogViewSet,
    basename="budget-stage",
)

router.register(
    "budget-sheets",
    BudgetSheetViewSet,
    basename="budget-sheet",
)
router.register(
    "supplies",
    SupplyViewSet,
    basename="supply",
)
router.register(
    "composition-groups",
    ServiceCompositionGroupViewSet,
    basename="composition-group",
)
router.register(
    "service-compositions",
    ServiceCompositionViewSet,
    basename="service-composition",
)
router.register(
    "measurement-units",
    UnitMeasureViewSet,
    basename="measurement-unit",
)
router.register(
    "material-groups",
    MaterialGroupViewSet,
    basename="material-group",
)
router.register(
    "supply-types",
    SupplyTypeViewSet,
    basename="supply-type",
)

urlpatterns = router.urls
