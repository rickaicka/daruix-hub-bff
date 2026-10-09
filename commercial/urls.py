from rest_framework.routers import DefaultRouter

from commercial.views import (
    AddressViewSet,
    BusinessSegmentViewSet,
    CompanyTypeViewSet,
    ContactViewSet,
    DepartmentViewSet,
    DivisionViewSet,
    PartyViewSet,
    ProjectViewSet,
    ProposalContactViewSet,
    ProposalInstallmentViewSet,
    ProposalRequestedServiceViewSet,
    ProposalTypeViewSet,
    ProposalViewSet,
    ProposalWorkViewSet,
)

app_name = "commercial"
router = DefaultRouter()
router.register("parties", PartyViewSet, basename="party")
router.register("business-segments", BusinessSegmentViewSet, basename="business-segment")
router.register("company-types", CompanyTypeViewSet, basename="company-type")
router.register("divisions", DivisionViewSet, basename="division")
router.register("departments", DepartmentViewSet, basename="department")
router.register("projects", ProjectViewSet, basename="project")
router.register("proposal-types", ProposalTypeViewSet, basename="proposal-type")
router.register("addresses", AddressViewSet, basename="address")
router.register("contacts", ContactViewSet, basename="contact")
router.register("works", ProposalWorkViewSet, basename="work")
router.register("proposals", ProposalViewSet, basename="proposal")
router.register("proposal-requested-services", ProposalRequestedServiceViewSet, basename="proposal-requested-service")
router.register("proposal-contacts", ProposalContactViewSet, basename="proposal-contact")
router.register("proposal-installments", ProposalInstallmentViewSet, basename="proposal-installment")
urlpatterns = router.urls
