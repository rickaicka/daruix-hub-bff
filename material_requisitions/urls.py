from rest_framework.routers import DefaultRouter
from .views import MaterialRequisitionViewSet

app_name = "material_requisitions"
router = DefaultRouter()
router.register("", MaterialRequisitionViewSet, basename="material-requisition")
urlpatterns = router.urls
