from .invite_access import login_invitation
from .integration_api import hub_purchase_orders
from django.urls import path
from .activation import activate_supplier
from rest_framework.routers import SimpleRouter

from .views import MapView, SupplierRegistryView, SupplierView, PurchaseOrderDeliveryView
from .tender import TenderView

router = SimpleRouter()
router.register("suppliers", SupplierView, basename="quotation-supplier")
router.register("supplier-registry", SupplierRegistryView, basename="supplier-registry")
router.register("tenders", TenderView, basename="quotation-tender")
router.register("purchase-orders", PurchaseOrderDeliveryView, basename="quotation-purchase-order")
router.register("", MapView, basename="quotation-map")
from .opened_orders_api import opened_purchase_orders
urlpatterns = [path("opened-purchase-orders/", opened_purchase_orders, name="opened-purchase-orders")] + [path("integration/purchase-orders/", hub_purchase_orders, name="hub-purchase-orders-integration")] + router.urls
urlpatterns += [path("activate/<str:uid>/<str:token>/", activate_supplier, name="supplier-activate")]

urlpatterns += [path("invitation-login/", login_invitation, name="quotation-invitation-login")]
