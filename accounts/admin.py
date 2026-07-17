from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from accounts.models import (
    Client,
    Employee,
    GroupPermission,
    Permission,
    Supplier,
    User,
    UserGroup,
    HubModule,
    UserHubModuleFavorite,
)


class GroupPermissionInline(admin.TabularInline):
    model = GroupPermission
    extra = 0
    autocomplete_fields = ["permission"]
    fields = [
        "permission",
        "is_active",
    ]

    verbose_name = "Permissão do grupo"
    verbose_name_plural = "Permissões do grupo"


@admin.register(UserGroup)
class UserGroupAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user_type",
        "name",
        "is_active",
        "permissions_count",
        "created_at",
        "updated_at",
    ]

    list_filter = [
        "user_type",
        "is_active",
    ]

    search_fields = [
        "name",
        "description",
    ]

    ordering = [
        "user_type",
        "name",
    ]

    readonly_fields = [
        "created_at",
        "updated_at",
    ]

    fieldsets = (
        (
            "Grupo de usuário",
            {
                "fields": (
                    "user_type",
                    "name",
                    "description",
                    "is_active",
                )
            },
        ),
        (
            "Datas",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    inlines = [
        GroupPermissionInline,
    ]

    def permissions_count(self, obj):
        return obj.group_permissions.filter(
            is_active=True,
            permission__is_active=True,
        ).count()

    permissions_count.short_description = "Permissões ativas"


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "code",
        "module",
        "description",
        "is_active",
    ]

    list_filter = [
        "module",
        "is_active",
    ]

    search_fields = [
        "code",
        "description",
        "module",
    ]

    ordering = [
        "module",
        "code",
    ]

    fieldsets = (
        (
            "Permissão",
            {
                "fields": (
                    "code",
                    "module",
                    "description",
                    "is_active",
                )
            },
        ),
    )


@admin.register(GroupPermission)
class GroupPermissionAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "group",
        "group_user_type",
        "permission",
        "permission_module",
        "is_active",
    ]

    list_filter = [
        "group__user_type",
        "group",
        "permission__module",
        "is_active",
    ]

    search_fields = [
        "group__name",
        "group__description",
        "permission__code",
        "permission__description",
        "permission__module",
    ]

    autocomplete_fields = [
        "group",
        "permission",
    ]

    ordering = [
        "group__user_type",
        "group__name",
        "permission__module",
        "permission__code",
    ]

    fieldsets = (
        (
            "Permissão vinculada ao grupo",
            {
                "fields": (
                    "group",
                    "permission",
                    "is_active",
                )
            },
        ),
    )

    def group_user_type(self, obj):
        return obj.group.user_type

    group_user_type.short_description = "Tipo de usuário"

    def permission_module(self, obj):
        return obj.permission.module

    permission_module.short_description = "Módulo"


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    model = User

    list_display = [
        "id",
        "username",
        "email",
        "name",
        "user_type",
        "group",
        "is_active",
        "is_staff",
        "is_superuser",
        "user_origin",
    ]

    list_filter = [
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

    ordering = [
        "name",
    ]

    fieldsets = (
        (
            "Autenticação",
            {
                "fields": (
                    "username",
                    "email",
                    "password",
                )
            },
        ),
        (
            "Informações do usuário",
            {
                "fields": (
                    "name",
                    "user_type",
                    "group",
                    "is_active",
                )
            },
        ),
        (
            "Dados legados do Access",
            {
                "fields": (
                    "user_origin",
                    "legacy_id",
                    "legacy_username",
                    "legacy_group_name",
                    "is_migrated_from_access",
                    "migrated_at",
                    "last_legacy_login_at",
                    "last_legacy_sync_at",
                    "legacy_sync_enabled",
                )
            },
        ),
        (
            "Regras auxiliares legadas",
            {
                "fields": (
                    "approval_limit",
                    "can_access_dashboard",
                    "can_access_deductibles",
                )
            },
        ),
        (
            "Permissões administrativas do Django",
            {
                "classes": ("collapse",),
                "fields": (
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Datas",
            {
                "fields": (
                    "last_login",
                    "date_joined",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    readonly_fields = [
        "created_at",
        "updated_at",
        "migrated_at",
        "last_login",
        "date_joined",
    ]

    add_fieldsets = (
        (
            "Criar usuário",
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "name",
                    "user_type",
                    "group",
                    "password1",
                    "password2",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "client_group",
        "trade_name",
        "legal_name",
        "document",
        "is_active",
    ]

    list_filter = [
        "client_group",
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

    autocomplete_fields = [
        "user",
        "parent_client",
    ]

    fieldsets = (
        (
            "Cliente",
            {
                "fields": (
                    "user",
                    "client_group",
                    "parent_client",
                    "trade_name",
                    "legal_name",
                    "document",
                    "is_active",
                )
            },
        ),
    )


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "employee_subgroup",
        "department",
        "position",
        "is_active",
    ]

    list_filter = [
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

    autocomplete_fields = [
        "user",
    ]

    fieldsets = (
        (
            "Colaborador",
            {
                "fields": (
                    "user",
                    "employee_subgroup",
                    "department",
                    "position",
                    "is_active",
                )
            },
        ),
    )


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "trade_name",
        "legal_name",
        "document",
        "legacy_supplier_id",
        "is_active",
    ]

    list_filter = [
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

    autocomplete_fields = [
        "user",
    ]

    fieldsets = (
        (
            "Fornecedor",
            {
                "fields": (
                    "user",
                    "legacy_supplier_id",
                    "trade_name",
                    "legal_name",
                    "document",
                    "is_active",
                )
            },
        ),
    )

@admin.register(HubModule)
class HubModuleAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "slug",
        "route",
        "permission",
        "desktop_enabled",
        "mobile_enabled",
        "mfe_enabled",
        "legacy_enabled",
        "is_active",
        "order",
    ]

    list_filter = [
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
        "permission__code",
        "remote_name",
        "remote_entry",
    ]

    ordering = [
        "order",
        "name",
    ]

@admin.register(UserHubModuleFavorite)
class UserHubModuleFavoriteAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "module",
        "created_at",
    ]

    list_filter = [
        "module",
        "created_at",
    ]

    search_fields = [
        "user__username",
        "user__name",
        "user__email",
        "module__name",
        "module__slug",
    ]

    autocomplete_fields = [
        "user",
        "module",
    ]

    ordering = [
        "user__name",
        "module__order",
        "module__name",
    ]

    readonly_fields = [
        "created_at",
    ]