from rest_framework import serializers

from accounts.models import GroupPermission, Permission, UserGroup


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = [
            "id",
            "code",
            "module",
            "description",
            "is_active",
        ]


class UserGroupSerializer(serializers.ModelSerializer):
    permissions_count = serializers.SerializerMethodField()

    class Meta:
        model = UserGroup
        fields = [
            "id",
            "user_type",
            "name",
            "description",
            "is_active",
            "permissions_count",
            "created_at",
            "updated_at",
        ]

    def get_permissions_count(self, obj):
        return obj.group_permissions.filter(
            is_active=True,
            permission__is_active=True,
        ).count()


class GroupPermissionSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source="group.name", read_only=True)
    group_user_type = serializers.CharField(source="group.user_type", read_only=True)
    permission_code = serializers.CharField(source="permission.code", read_only=True)
    permission_module = serializers.CharField(source="permission.module", read_only=True)

    class Meta:
        model = GroupPermission
        fields = [
            "id",
            "group",
            "group_name",
            "group_user_type",
            "permission",
            "permission_code",
            "permission_module",
            "is_active",
        ]


class MyPermissionsSerializer(serializers.Serializer):
    permissions = serializers.ListField(
        child=serializers.CharField()
    )