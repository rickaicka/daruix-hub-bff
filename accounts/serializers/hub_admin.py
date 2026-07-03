from django.contrib.auth import get_user_model
from rest_framework import serializers

from accounts.models import (
    Client,
    Employee,
    GroupPermission,
    HubModule,
    Permission,
    Supplier,
    UserGroup,
)
from accounts.models.choices import UserType

User = get_user_model()


class AdminUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )

    group_name = serializers.CharField(
        source="group.name",
        read_only=True,
        allow_null=True,
    )

    permissions_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "password",
            "name",
            "user_type",
            "group",
            "group_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "user_origin",
            "legacy_id",
            "legacy_username",
            "legacy_group_name",
            "is_migrated_from_access",
            "migrated_at",
            "last_legacy_login_at",
            "last_legacy_sync_at",
            "legacy_sync_enabled",
            "approval_limit",
            "can_access_dashboard",
            "can_access_deductibles",
            "permissions_count",
            "last_login",
            "date_joined",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "migrated_at",
            "last_login",
            "date_joined",
            "created_at",
            "updated_at",
            "permissions_count",
        ]

    def get_permissions_count(self, obj):
        if not obj.group:
            return 0

        return obj.group.group_permissions.filter(
            is_active=True,
            permission__is_active=True,
        ).count()

    def validate(self, attrs):
        user_type = attrs.get(
            "user_type",
            getattr(self.instance, "user_type", None),
        )

        group = attrs.get(
            "group",
            getattr(self.instance, "group", None),
        )

        if group and user_type and group.user_type != user_type:
            raise serializers.ValidationError({
                "group": "O grupo selecionado não pertence ao tipo de usuário informado."
            })

        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password", None)

        if not password:
            raise serializers.ValidationError({
                "password": "A senha é obrigatória para criar um usuário."
            })

        user = User(**validated_data)
        user.set_password(password)
        user.save()

        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)

        if password:
            instance.set_password(password)

        instance.save()

        return instance


class AdminHubModuleSerializer(serializers.ModelSerializer):
    permission_code = serializers.CharField(
        source="permission.code",
        read_only=True,
    )

    permission_description = serializers.CharField(
        source="permission.description",
        read_only=True,
    )

    class Meta:
        model = HubModule
        fields = [
            "id",
            "name",
            "slug",
            "route",
            "icon",
            "permission",
            "permission_code",
            "permission_description",
            "desktop_enabled",
            "mobile_enabled",
            "mfe_enabled",
            "legacy_enabled",
            "remote_name",
            "remote_entry",
            "exposed_module",
            "order",
            "is_active",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]


class AdminPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = [
            "id",
            "code",
            "module",
            "description",
            "is_active",
        ]


class AdminUserGroupSerializer(serializers.ModelSerializer):
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

        read_only_fields = [
            "id",
            "permissions_count",
            "created_at",
            "updated_at",
        ]

    def get_permissions_count(self, obj):
        return obj.group_permissions.filter(
            is_active=True,
            permission__is_active=True,
        ).count()


class AdminGroupPermissionSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(
        source="group.name",
        read_only=True,
    )

    group_user_type = serializers.CharField(
        source="group.user_type",
        read_only=True,
    )

    permission_code = serializers.CharField(
        source="permission.code",
        read_only=True,
    )

    permission_module = serializers.CharField(
        source="permission.module",
        read_only=True,
    )

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


class AdminClientSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(
        source="user.name",
        read_only=True,
    )

    user_email = serializers.EmailField(
        source="user.email",
        read_only=True,
    )

    class Meta:
        model = Client
        fields = [
            "id",
            "user",
            "user_name",
            "user_email",
            "client_group",
            "parent_client",
            "trade_name",
            "legal_name",
            "document",
            "is_active",
        ]


class AdminEmployeeSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(
        source="user.name",
        read_only=True,
    )

    user_email = serializers.EmailField(
        source="user.email",
        read_only=True,
    )

    class Meta:
        model = Employee
        fields = [
            "id",
            "user",
            "user_name",
            "user_email",
            "employee_subgroup",
            "department",
            "position",
            "is_active",
        ]


class AdminSupplierSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(
        source="user.name",
        read_only=True,
    )

    user_email = serializers.EmailField(
        source="user.email",
        read_only=True,
    )

    class Meta:
        model = Supplier
        fields = [
            "id",
            "user",
            "user_name",
            "user_email",
            "legacy_supplier_id",
            "trade_name",
            "legal_name",
            "document",
            "is_active",
        ]