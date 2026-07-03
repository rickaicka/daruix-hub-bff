from django.contrib.auth import get_user_model
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from accounts.models import (
    Client,
    Employee,
    GroupPermission,
    HubModule,
    Permission,
    Supplier,
    UserGroup,
)
from accounts.models.choices import ClientGroup, EmployeeGroup, UserType
from accounts.serializers.hub_admin import (
    AdminClientSerializer,
    AdminEmployeeSerializer,
    AdminGroupPermissionSerializer,
    AdminHubModuleSerializer,
    AdminPermissionSerializer,
    AdminSupplierSerializer,
    AdminUserGroupSerializer,
    AdminUserSerializer,
)
from accounts.serializers.hub_module_serializer import HubModuleSerializer
from accounts.services.hub_module_service import get_user_modules
from accounts.services.permission_service import get_user_permission_codes

User = get_user_model()


def choices_to_payload(choices):
    return [
        {
            "value": value,
            "label": label,
        }
        for value, label in choices
    ]


class HubAdminOptionsView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["hub-admin/opcoes"],
        summary="Listar opções administrativas",
        description=(
            "Retorna opções usadas em selects administrativos, "
            "como tipos de usuário, grupos de cliente, grupos de colaborador "
            "e origens de usuário."
        ),
    )
    def get(self, request):
        return Response({
            "user_types": choices_to_payload(UserType.choices),
            "client_groups": choices_to_payload(ClientGroup.choices),
            "employee_groups": choices_to_payload(EmployeeGroup.choices),
            "user_origins": choices_to_payload(User.USER_ORIGIN_CHOICES),
        })


@extend_schema_view(
    list=extend_schema(
        tags=["hub-admin/usuarios"],
        summary="Listar usuários",
    ),
    retrieve=extend_schema(
        tags=["hub-admin/usuarios"],
        summary="Detalhar usuário",
    ),
    create=extend_schema(
        tags=["hub-admin/usuarios"],
        summary="Criar usuário",
    ),
    update=extend_schema(
        tags=["hub-admin/usuarios"],
        summary="Atualizar usuário",
    ),
    partial_update=extend_schema(
        tags=["hub-admin/usuarios"],
        summary="Atualizar parcialmente usuário",
    ),
    destroy=extend_schema(
        tags=["hub-admin/usuarios"],
        summary="Remover usuário",
    ),
    permissions=extend_schema(
        tags=["hub-admin/usuarios"],
        summary="Listar permissões efetivas do usuário",
    ),
    modules=extend_schema(
        tags=["hub-admin/usuarios"],
        summary="Listar módulos acessíveis pelo usuário",
    ),
)
class AdminUserViewSet(ModelViewSet):
    queryset = (
        User.objects
        .select_related("group")
        .all()
        .order_by("name")
    )

    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminUser]

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_fields = [
        "user_type",
        "group",
        "is_active",
        "is_staff",
        "is_superuser",
        "user_origin",
        "is_migrated_from_access",
    ]

    search_fields = [
        "username",
        "email",
        "name",
        "legacy_username",
        "legacy_group_name",
    ]

    ordering_fields = [
        "id",
        "name",
        "username",
        "email",
        "user_type",
        "date_joined",
        "last_login",
    ]

    @action(
        detail=True,
        methods=["get"],
        url_path="permissoes",
    )
    def permissions(self, request, pk=None):
        user = self.get_object()

        return Response({
            "user_id": user.id,
            "permissions": get_user_permission_codes(user),
        })

    @action(
        detail=True,
        methods=["get"],
        url_path="modulos",
    )
    def modules(self, request, pk=None):
        user = self.get_object()
        modules = get_user_modules(user)

        return Response({
            "user_id": user.id,
            "modules": HubModuleSerializer(modules, many=True).data,
        })


@extend_schema_view(
    list=extend_schema(
        tags=["hub-admin/modulos"],
        summary="Listar módulos do Hub",
    ),
    retrieve=extend_schema(
        tags=["hub-admin/modulos"],
        summary="Detalhar módulo do Hub",
    ),
    create=extend_schema(
        tags=["hub-admin/modulos"],
        summary="Criar módulo do Hub",
    ),
    update=extend_schema(
        tags=["hub-admin/modulos"],
        summary="Atualizar módulo do Hub",
    ),
    partial_update=extend_schema(
        tags=["hub-admin/modulos"],
        summary="Atualizar parcialmente módulo do Hub",
    ),
    destroy=extend_schema(
        tags=["hub-admin/modulos"],
        summary="Remover módulo do Hub",
    ),
)
class AdminHubModuleViewSet(ModelViewSet):
    queryset = (
        HubModule.objects
        .select_related("permission")
        .all()
        .order_by("order", "name")
    )

    serializer_class = AdminHubModuleSerializer
    permission_classes = [IsAdminUser]

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_fields = [
        "permission",
        "desktop_enabled",
        "mobile_enabled",
        "mfe_enabled",
        "legacy_enabled",
        "is_active",
    ]

    search_fields = [
        "name",
        "slug",
        "route",
        "icon",
        "permission__code",
        "remote_name",
        "remote_entry",
    ]

    ordering_fields = [
        "id",
        "order",
        "name",
        "slug",
    ]


@extend_schema_view(
    list=extend_schema(
        tags=["hub-admin/permissoes"],
        summary="Listar permissões",
    ),
    retrieve=extend_schema(
        tags=["hub-admin/permissoes"],
        summary="Detalhar permissão",
    ),
    create=extend_schema(
        tags=["hub-admin/permissoes"],
        summary="Criar permissão",
    ),
    update=extend_schema(
        tags=["hub-admin/permissoes"],
        summary="Atualizar permissão",
    ),
    partial_update=extend_schema(
        tags=["hub-admin/permissoes"],
        summary="Atualizar parcialmente permissão",
    ),
    destroy=extend_schema(
        tags=["hub-admin/permissoes"],
        summary="Remover permissão",
    ),
)
class AdminPermissionViewSet(ModelViewSet):
    queryset = Permission.objects.all().order_by("module", "code")
    serializer_class = AdminPermissionSerializer
    permission_classes = [IsAdminUser]

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_fields = [
        "module",
        "is_active",
    ]

    search_fields = [
        "code",
        "module",
        "description",
    ]

    ordering_fields = [
        "id",
        "module",
        "code",
    ]


@extend_schema_view(
    list=extend_schema(
        tags=["hub-admin/grupos"],
        summary="Listar grupos de usuário",
    ),
    retrieve=extend_schema(
        tags=["hub-admin/grupos"],
        summary="Detalhar grupo de usuário",
    ),
    create=extend_schema(
        tags=["hub-admin/grupos"],
        summary="Criar grupo de usuário",
    ),
    update=extend_schema(
        tags=["hub-admin/grupos"],
        summary="Atualizar grupo de usuário",
    ),
    partial_update=extend_schema(
        tags=["hub-admin/grupos"],
        summary="Atualizar parcialmente grupo de usuário",
    ),
    destroy=extend_schema(
        tags=["hub-admin/grupos"],
        summary="Remover grupo de usuário",
    ),
)
class AdminUserGroupViewSet(ModelViewSet):
    queryset = UserGroup.objects.all().order_by("user_type", "name")
    serializer_class = AdminUserGroupSerializer
    permission_classes = [IsAdminUser]

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_fields = [
        "user_type",
        "is_active",
    ]

    search_fields = [
        "name",
        "description",
    ]

    ordering_fields = [
        "id",
        "user_type",
        "name",
    ]


@extend_schema_view(
    list=extend_schema(
        tags=["hub-admin/grupo-permissoes"],
        summary="Listar permissões vinculadas a grupos",
    ),
    retrieve=extend_schema(
        tags=["hub-admin/grupo-permissoes"],
        summary="Detalhar permissão vinculada a grupo",
    ),
    create=extend_schema(
        tags=["hub-admin/grupo-permissoes"],
        summary="Vincular permissão a grupo",
    ),
    update=extend_schema(
        tags=["hub-admin/grupo-permissoes"],
        summary="Atualizar permissão vinculada a grupo",
    ),
    partial_update=extend_schema(
        tags=["hub-admin/grupo-permissoes"],
        summary="Atualizar parcialmente permissão vinculada a grupo",
    ),
    destroy=extend_schema(
        tags=["hub-admin/grupo-permissoes"],
        summary="Remover permissão vinculada a grupo",
    ),
)
class AdminGroupPermissionViewSet(ModelViewSet):
    queryset = (
        GroupPermission.objects
        .select_related("group", "permission")
        .all()
        .order_by(
            "group__user_type",
            "group__name",
            "permission__module",
            "permission__code",
        )
    )

    serializer_class = AdminGroupPermissionSerializer
    permission_classes = [IsAdminUser]

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_fields = [
        "group",
        "group__user_type",
        "permission",
        "permission__module",
        "is_active",
    ]

    search_fields = [
        "group__name",
        "permission__code",
        "permission__module",
        "permission__description",
    ]


@extend_schema_view(
    list=extend_schema(
        tags=["hub-admin/clientes"],
        summary="Listar clientes",
    ),
    retrieve=extend_schema(
        tags=["hub-admin/clientes"],
        summary="Detalhar cliente",
    ),
    create=extend_schema(
        tags=["hub-admin/clientes"],
        summary="Criar cliente",
    ),
    update=extend_schema(
        tags=["hub-admin/clientes"],
        summary="Atualizar cliente",
    ),
    partial_update=extend_schema(
        tags=["hub-admin/clientes"],
        summary="Atualizar parcialmente cliente",
    ),
    destroy=extend_schema(
        tags=["hub-admin/clientes"],
        summary="Remover cliente",
    ),
)
class AdminClientViewSet(ModelViewSet):
    queryset = (
        Client.objects
        .select_related("user", "parent_client")
        .all()
        .order_by("trade_name", "legal_name")
    )

    serializer_class = AdminClientSerializer
    permission_classes = [IsAdminUser]

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_fields = [
        "client_group",
        "parent_client",
        "is_active",
    ]

    search_fields = [
        "user__username",
        "user__name",
        "user__email",
        "trade_name",
        "legal_name",
        "document",
    ]


@extend_schema_view(
    list=extend_schema(
        tags=["hub-admin/colaboradores"],
        summary="Listar colaboradores",
    ),
    retrieve=extend_schema(
        tags=["hub-admin/colaboradores"],
        summary="Detalhar colaborador",
    ),
    create=extend_schema(
        tags=["hub-admin/colaboradores"],
        summary="Criar colaborador",
    ),
    update=extend_schema(
        tags=["hub-admin/colaboradores"],
        summary="Atualizar colaborador",
    ),
    partial_update=extend_schema(
        tags=["hub-admin/colaboradores"],
        summary="Atualizar parcialmente colaborador",
    ),
    destroy=extend_schema(
        tags=["hub-admin/colaboradores"],
        summary="Remover colaborador",
    ),
)
class AdminEmployeeViewSet(ModelViewSet):
    queryset = (
        Employee.objects
        .select_related("user")
        .all()
        .order_by("user__name")
    )

    serializer_class = AdminEmployeeSerializer
    permission_classes = [IsAdminUser]

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_fields = [
        "employee_subgroup",
        "department",
        "is_active",
    ]

    search_fields = [
        "user__username",
        "user__name",
        "user__email",
        "department",
        "position",
    ]


@extend_schema_view(
    list=extend_schema(
        tags=["hub-admin/fornecedores"],
        summary="Listar fornecedores",
    ),
    retrieve=extend_schema(
        tags=["hub-admin/fornecedores"],
        summary="Detalhar fornecedor",
    ),
    create=extend_schema(
        tags=["hub-admin/fornecedores"],
        summary="Criar fornecedor",
    ),
    update=extend_schema(
        tags=["hub-admin/fornecedores"],
        summary="Atualizar fornecedor",
    ),
    partial_update=extend_schema(
        tags=["hub-admin/fornecedores"],
        summary="Atualizar parcialmente fornecedor",
    ),
    destroy=extend_schema(
        tags=["hub-admin/fornecedores"],
        summary="Remover fornecedor",
    ),
)
class AdminSupplierViewSet(ModelViewSet):
    queryset = (
        Supplier.objects
        .select_related("user")
        .all()
        .order_by("trade_name", "legal_name")
    )

    serializer_class = AdminSupplierSerializer
    permission_classes = [IsAdminUser]

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_fields = [
        "is_active",
    ]

    search_fields = [
        "user__username",
        "user__name",
        "user__email",
        "trade_name",
        "legal_name",
        "document",
        "legacy_supplier_id",
    ]