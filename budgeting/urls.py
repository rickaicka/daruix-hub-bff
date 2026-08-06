from rest_framework.routers import DefaultRouter

from .views import ServiceCompositionViewSet, SupplyViewSet

app_name = "budgeting"

router = DefaultRouter()
router.register("supplies", SupplyViewSet, basename="supply")
router.register("service-compositions", ServiceCompositionViewSet, basename="service-composition")

urlpatterns = router.urls

