from django.urls import include, path
from rest_framework.routers import DefaultRouter

from memorando_remessas.views import (
    LegacyClientListView,
    LegacyWorkDetailView,
    LegacyWorkListView,
    MemorandoRemessasHealthView,
    ShipmentMemoOptionsView,
    ShipmentMemoResponsibleUsersView,
    ShipmentMemoViewSet,
)


app_name = "memorando_remessas"


router = DefaultRouter()

router.register(
    r"memorandos",
    ShipmentMemoViewSet,
    basename="shipment-memo",
)


urlpatterns = [
    path(
        "health/",
        MemorandoRemessasHealthView.as_view(),
        name="health",
    ),

    path(
        "opcoes/",
        ShipmentMemoOptionsView.as_view(),
        name="shipment-memo-options",
    ),

    path(
        "responsaveis/",
        ShipmentMemoResponsibleUsersView.as_view(),
        name="shipment-memo-responsible-users",
    ),

    path(
        "legado/clientes/",
        LegacyClientListView.as_view(),
        name="legacy-client-list",
    ),

    path(
        "legado/obras/",
        LegacyWorkListView.as_view(),
        name="legacy-work-list",
    ),

    path(
        "legado/obras/<int:legacy_work_id>/",
        LegacyWorkDetailView.as_view(),
        name="legacy-work-detail",
    ),

    path(
        "",
        include(router.urls),
    ),
]