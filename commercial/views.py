from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.utils import timezone
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from commercial.models import (
    Address,
    BusinessSegment,
    CompanyType,
    Contact,
    Department,
    Division,
    Party,
    PartyType,
    Proposal,
    ProposalContact,
    ProposalInstallment,
    ProposalRequestedService,
    ProposalType,
    Project,
)
from commercial.pagination import (
    CommercialAutocompletePagination,
    CommercialPagination,
)
from commercial.serializers import (
    AddressSerializer,
    BusinessSegmentSerializer,
    ClientFullSerializer,
    CompanyTypeSerializer,
    ContactSerializer,
    DepartmentSerializer,
    DivisionSerializer,
    PartyAutocompleteSerializer,
    PartySerializer,

    ProposalWorkAutocompleteSerializer,

    ProposalSerializer,
    ProposalContactSerializer,
    ProposalInstallmentSerializer,
    ProposalRequestedServiceSerializer,
    ProposalTypeSerializer,
    ProjectSerializer,
)
from commercial.services.parties import (
    PartyChildNotFoundError,
)
from commercial.services.proposals import (
    accept_proposal,
)


class PartyViewSet(viewsets.ModelViewSet):
    queryset = (
        Party.objects
        .select_related(
            "business_segment",
            "company_type",
        )
        .prefetch_related(
            "addresses",
            "contacts",
        )
        .filter(is_active=True)
    )

    serializer_class = PartySerializer
    pagination_class = CommercialPagination

    filter_backends = (
        filters.SearchFilter,
        filters.OrderingFilter,
    )

    search_fields = (
        "legal_name",
        "trade_name",
        "document",
    )

    ordering_fields = (
        "legal_name",
        "trade_name",
        "document",
        "created_at",
        "updated_at",
        "id",
    )

    ordering = (
        "legal_name",
        "id",
    )

    def get_serializer_class(self):
        if self.action == "clients":
            return PartyAutocompleteSerializer

        if self.action in (
            "create_client_full",
            "full",
        ):
            return ClientFullSerializer

        if self.action == "autocomplete":
            return PartyAutocompleteSerializer

        return PartySerializer

    def get_pagination_class(self):
        if self.action in (
            "autocomplete",
            "clients",
        ):
            return CommercialAutocompletePagination

        return CommercialPagination

    def paginate_queryset(self, queryset):
        pagination_class = (
            self.get_pagination_class()
        )

        if pagination_class is None:
            return None

        if (
            not hasattr(
                self,
                "_commercial_paginator",
            )
            or not isinstance(
                self._commercial_paginator,
                pagination_class,
            )
        ):
            self._commercial_paginator = (
                pagination_class()
            )

        return (
            self._commercial_paginator
            .paginate_queryset(
                queryset,
                self.request,
                view=self,
            )
        )

    def get_paginated_response(self, data):
        return (
            self._commercial_paginator
            .get_paginated_response(data)
        )

    def perform_create(self, serializer):
        serializer.save(
            created_by=self.request.user,
            updated_by=self.request.user,
        )

    def perform_update(self, serializer):
        serializer.save(
            updated_by=self.request.user,
        )

    @action(
        detail=False,
        methods=("get",),
    )
    def autocomplete(self, request):
        term = request.query_params.get(
            "search",
            "",
        ).strip()

        queryset = self.get_queryset()

        if term:
            queryset = queryset.filter(
                Q(
                    legal_name__icontains=term
                )
                | Q(
                    trade_name__icontains=term
                )
                | Q(
                    document__icontains=term
                )
            )

        page = self.paginate_queryset(
            queryset
        )

        serializer = self.get_serializer(
            page,
            many=True,
        )

        return self.get_paginated_response(
            serializer.data
        )

    @action(
        detail=False,
        methods=("get",),
    )
    def clients(self, request):
        term = request.query_params.get(
            "search",
            "",
        ).strip()

        queryset = self.get_queryset().filter(
            party_type=PartyType.CLIENT
        )

        if term:
            queryset = queryset.filter(
                Q(
                    legal_name__icontains=term
                )
                | Q(
                    trade_name__icontains=term
                )
                | Q(
                    document__icontains=term
                )
            )

        page = self.paginate_queryset(
            queryset
        )

        serializer = self.get_serializer(
            page,
            many=True,
        )

        return self.get_paginated_response(
            serializer.data
        )

    @action(
        detail=False,
        methods=("post",),
        url_path="clients/full",
    )
    def create_client_full(
        self,
        request,
    ):
        serializer = self.get_serializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True
        )

        try:
            instance = serializer.save()

        except PartyChildNotFoundError as error:
            return Response(
                {
                    "detail": str(error),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        output = self.get_serializer(
            instance
        )

        return Response(
            output.data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=("get", "put", "patch"),
        url_path="full",
    )
    def full(
        self,
        request,
        pk=None,
    ):
        instance = self.get_object()

        if instance.party_type != PartyType.CLIENT:
            return Response(
                {
                    "detail": (
                        "O registro informado não é um cliente."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.method == "GET":
            return Response(
                self.get_serializer(
                    instance
                ).data
            )

        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=request.method == "PATCH",
        )

        serializer.is_valid(
            raise_exception=True
        )

        try:
            instance = serializer.save()

        except PartyChildNotFoundError as error:
            return Response(
                {
                    "detail": str(error),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            self.get_serializer(
                instance
            ).data
        )


class CommercialCatalogViewSet(
    viewsets.ReadOnlyModelViewSet
):
    pagination_class = CommercialPagination

    filter_backends = (
        filters.SearchFilter,
        filters.OrderingFilter,
    )

    search_fields = (
        "name",
    )

    ordering_fields = (
        "name",
        "legacy_id",
        "id",
    )

    ordering = (
        "name",
        "id",
    )


class BusinessSegmentViewSet(
    CommercialCatalogViewSet
):
    queryset = BusinessSegment.objects.filter(
        is_active=True
    )

    serializer_class = (
        BusinessSegmentSerializer
    )


class CompanyTypeViewSet(
    CommercialCatalogViewSet
):
    queryset = CompanyType.objects.filter(
        is_active=True
    )

    serializer_class = (
        CompanyTypeSerializer
    )


class DivisionViewSet(CommercialCatalogViewSet):
    queryset = Division.objects.filter(is_active=True)
    serializer_class = DivisionSerializer
    search_fields = ("name", "code")
    ordering_fields = ("name", "code", "legacy_id", "id")


class DepartmentViewSet(CommercialCatalogViewSet):
    serializer_class = DepartmentSerializer

    def get_queryset(self):
        queryset = Department.objects.select_related("division").filter(is_active=True)
        division_id = self.request.query_params.get("division")
        return queryset.filter(division_id=division_id) if division_id else queryset


class ProjectViewSet(CommercialCatalogViewSet):
    serializer_class = ProjectSerializer

    def get_queryset(self):
        queryset = Project.objects.select_related("department").filter(is_active=True)
        department_id = self.request.query_params.get("department")
        return queryset.filter(department_id=department_id) if department_id else queryset


class ProposalTypeViewSet(CommercialCatalogViewSet):
    queryset = ProposalType.objects.filter(is_active=True)
    serializer_class = ProposalTypeSerializer


class PartyChildViewSetMixin:
    pagination_class = CommercialPagination

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .filter(is_active=True)
        )

        party_id = (
            self.request
            .query_params
            .get("party")
        )

        if not party_id:
            return queryset.none()

        return queryset.filter(
            party_id=party_id
        )


class AddressViewSet(
    PartyChildViewSetMixin,
    viewsets.ModelViewSet,
):
    queryset = (
        Address.objects
        .select_related("party")
        .order_by("id")
    )

    serializer_class = AddressSerializer


class ContactViewSet(
    PartyChildViewSetMixin,
    viewsets.ModelViewSet,
):
    queryset = (
        Contact.objects
        .select_related(
            "party"
        )
        .order_by(
            "name",
            "id",
        )
    )

    serializer_class = (
        ContactSerializer
    )

    pagination_class = (
        CommercialAutocompletePagination
    )

    filter_backends = (
        filters.SearchFilter,
        filters.OrderingFilter,
    )

    search_fields = (
        "name",
        "position",
        "email",
        "phone",
        "mobile",
    )

    ordering_fields = (
        "name",
        "position",
        "email",
        "id",
    )

    ordering = (
        "name",
        "id",
    )

class ProposalWorkViewSet(
    viewsets.ReadOnlyModelViewSet
):
    """
    Autocomplete de obras conhecidas do cliente/interessado.

    GET:
    /api/commercial/works/
        ?party=123
        &search=ipiranga
        &page=1
        &page_size=20
    """

    serializer_class = (
        ProposalWorkAutocompleteSerializer
    )

    pagination_class = (
        CommercialAutocompletePagination
    )

    def get_queryset(self):
        queryset = (
            Proposal.objects
            .select_related(
                "work_address",
            )
            .exclude(
                work_name="",
            )
        )

        party_id = (
            self.request
            .query_params
            .get(
                "party"
            )
        )

        if not party_id:
            return queryset.none()

        queryset = queryset.filter(
            party_id=party_id
        )

        term = (
            self.request
            .query_params
            .get(
                "search",
                "",
            )
            .strip()
        )

        if term:
            queryset = queryset.filter(
                Q(
                    work_name__icontains=term
                )
                |
                Q(
                    code__icontains=term
                )
            )

        return queryset.order_by(
            "work_name",
            "-entry_date",
            "-id",
        )

class ProposalViewSet(
    viewsets.ModelViewSet
):
    queryset = (
        Proposal.objects
        .select_related(
            "party",
            "work_address",
            "requester_contact",
            "division",
            "department",
            "proposal_type",
            "technical_responsible",
            "issuer",
        )
        .prefetch_related(
            "party__addresses",
            "requested_services__project__department",
            "proposal_contacts__contact",
            "installments",
        )
    )

    serializer_class = ProposalSerializer
    pagination_class = CommercialPagination

    filter_backends = (
        filters.SearchFilter,
        filters.OrderingFilter,
    )

    search_fields = (
        "code",
        "party__legal_name",
        "party__trade_name",
        "work_name",
    )

    ordering_fields = (
        "code",
        "status",
        "entry_date",
        "id",
    )

    ordering = (
        "-entry_date",
        "-id",
    )

    def get_queryset(self):
        queryset = super().get_queryset()

        code = self.request.query_params.get("code", "").strip()
        client = self.request.query_params.get("client", "").strip()
        work = self.request.query_params.get("work", "").strip()
        status_value = self.request.query_params.get("status", "").strip()
        entry_date = self.request.query_params.get("entry_date", "").strip()

        if code:
            queryset = queryset.filter(code__icontains=code)

        if client:
            queryset = queryset.filter(
                Q(party__legal_name__icontains=client)
                | Q(party__trade_name__icontains=client)
            )

        if work:
            queryset = queryset.filter(work_name__icontains=work)

        if status_value:
            queryset = queryset.filter(status=status_value)

        if entry_date:
            queryset = queryset.filter(entry_date=entry_date)

        return queryset

    def perform_create(self, serializer):
        issuer = serializer.validated_data.get("issuer")
        issuer_name = str(
            serializer.validated_data.get("issuer_name") or ""
        ).strip()

        if issuer is None and not issuer_name:
            serializer.save(issuer=self.request.user)
            return

        serializer.save()

    @action(
        detail=False,
        methods=("get",),
        url_path="pc-status",
    )
    def pc_status(self, request):
        raw_code = request.query_params.get("code", "").strip()
        year = timezone.localdate().strftime("%y")

        try:
            last_code = Proposal.last_current_year_code()
            next_code = Proposal.next_available_code()
        except DjangoValidationError as error:
            return Response(
                {"detail": self._validation_message(error, "code")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not raw_code:
            return Response(
                {
                    "year": year,
                    "last_code": last_code,
                    "next_code": next_code,
                    "code": next_code,
                    "valid": True,
                    "exists": False,
                    "message": None,
                }
            )

        code = Proposal.normalize_pc_code(raw_code)
        exists = Proposal.objects.filter(code=code).exists()

        try:
            validated_code = Proposal.validate_new_code(code)
        except DjangoValidationError as error:
            return Response(
                {
                    "year": year,
                    "last_code": last_code,
                    "next_code": next_code,
                    "code": code,
                    "valid": False,
                    "exists": exists,
                    "message": self._validation_message(error, "code"),
                }
            )

        return Response(
            {
                "year": year,
                "last_code": last_code,
                "next_code": next_code,
                "code": validated_code,
                "valid": True,
                "exists": False,
                "message": None,
            }
        )

    @staticmethod
    def _validation_message(error, field):
        if hasattr(error, "message_dict"):
            messages = error.message_dict.get(field) or error.messages
        else:
            messages = error.messages

        return messages[0] if messages else "Valor inválido."

    @action(
        detail=True,
        methods=("post",),
    )
    def accept(
        self,
        request,
        pk=None,
    ):
        proposal = accept_proposal(
            proposal=self.get_object()
        )

        return Response(
            self.get_serializer(
                proposal
            ).data
        )


class ProposalChildViewSetMixin:
    pagination_class = CommercialPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        proposal_id = self.request.query_params.get("proposal")
        return queryset.filter(proposal_id=proposal_id) if proposal_id else queryset.none()


class ProposalRequestedServiceViewSet(
    ProposalChildViewSetMixin,
    viewsets.ModelViewSet,
):
    queryset = ProposalRequestedService.objects.select_related(
        "proposal",
        "project",
        "project__department",
    )
    serializer_class = ProposalRequestedServiceSerializer


class ProposalContactViewSet(
    ProposalChildViewSetMixin,
    viewsets.ModelViewSet,
):
    queryset = ProposalContact.objects.select_related(
        "proposal",
        "contact",
        "contact__party",
    )
    serializer_class = ProposalContactSerializer


class ProposalInstallmentViewSet(
    ProposalChildViewSetMixin,
    viewsets.ModelViewSet,
):
    queryset = ProposalInstallment.objects.select_related("proposal")
    serializer_class = ProposalInstallmentSerializer
