from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from accounts.models import GroupPermission, Permission, UserGroup
from accounts.serializers.permissioning import (
    GroupPermissionSerializer,
    MyPermissionsSerializer,
    PermissionSerializer,
    UserGroupSerializer,
)
from accounts.services.permission_service import get_user_permission_codes


class PermissionViewSet(ModelViewSet):
    queryset = Permission.objects.all().order_by("module", "code")
    serializer_class = PermissionSerializer
    permission_classes = [IsAdminUser]
    search_fields = [
        "code",
        "module",
        "description",
    ]
    filterset_fields = [
        "module",
        "is_active",
    ]


class UserGroupViewSet(ModelViewSet):
    queryset = UserGroup.objects.all().order_by("user_type", "name")
    serializer_class = UserGroupSerializer
    permission_classes = [IsAdminUser]
    search_fields = [
        "name",
        "description",
    ]
    filterset_fields = [
        "user_type",
        "is_active",
    ]


class GroupPermissionViewSet(ModelViewSet):
    queryset = (
        GroupPermission.objects.select_related("group", "permission")
        .all()
        .order_by(
            "group__user_type",
            "group__name",
            "permission__module",
            "permission__code",
        )
    )
    serializer_class = GroupPermissionSerializer
    permission_classes = [IsAdminUser]
    search_fields = [
        "group__name",
        "permission__code",
        "permission__module",
        "permission__description",
    ]
    filterset_fields = [
        "group",
        "group__user_type",
        "permission__module",
        "is_active",
    ]


class MyPermissionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        permissions = get_user_permission_codes(request.user)

        serializer = MyPermissionsSerializer(
            {
                "permissions": permissions,
            }
        )

        return Response(serializer.data)

