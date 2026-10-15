from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.admin.utils import get_deleted_objects
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models.deletion import ProtectedError, RestrictedError
from django.template.response import TemplateResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html

from accounts.models import (
    Client,
    Employee,
    GroupPermission,
    Permission,
    Supplier,
    User,
    UserGroup,
    HubMenuItem,
    HubModule,
    UserHubMenuItemFavorite,
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

    # Exclusao padrao = soft delete. Excecao explicita, apenas no Admin: hard delete.
    actions = ["soft_delete_users", "reactivate_users", "hard_delete_user"]

    def _eligible_users(self, request, queryset):
        # Protect current account and superusers from accidental deactivation.
        return queryset.exclude(pk=request.user.pk).exclude(is_superuser=True)

    def has_delete_permission(self, request, obj=None):
        if not super().has_delete_permission(request, obj):
            return False
        if obj is not None and (obj.pk == request.user.pk or obj.is_superuser):
            return False
        return True

    def get_deleted_objects(self, objs, request):
        # No dependent objects will be physically deleted by a soft delete.
        return [], {}, set(), []

    def delete_model(self, request, obj):
        if not self.has_delete_permission(request, obj):
            raise PermissionDenied
        obj.is_active = False
        obj.save(update_fields=["is_active"])

    def delete_queryset(self, request, queryset):
        if not self.has_delete_permission(request):
            raise PermissionDenied
        self._eligible_users(request, queryset).update(is_active=False)

    def response_delete(self, request, obj_display, obj_id):
        self.message_user(
            request,
            f'Usuário "{obj_display}" desativado (soft delete). Nenhum vínculo foi removido.',
            messages.SUCCESS,
        )
        return redirect(reverse("admin:accounts_user_changelist"))

    @admin.action(description="Excluir selecionados (soft delete, preservar vínculos)")
    def soft_delete_users(self, request, queryset):
        if not self.has_delete_permission(request):
            raise PermissionDenied
        eligible = self._eligible_users(request, queryset)
        count = eligible.filter(is_active=True).update(is_active=False)
        self.message_user(
            request,
            f"{count} usuário(s) desativado(s). Históricos e arquivos preservados.",
            messages.SUCCESS,
        )

    @admin.action(description="Reativar usuários selecionados")
    def reactivate_users(self, request, queryset):
        if not self.has_change_permission(request):
            raise PermissionDenied
        count = self._eligible_users(request, queryset).filter(is_active=False).update(is_active=True)
        self.message_user(request, f"{count} usuário(s) reativado(s).", messages.SUCCESS)

    @admin.action(description="EXCLUIR DEFINITIVAMENTE um usuario (irreversivel)")
    def hard_delete_user(self, request, queryset):
        # Restrito ao Django Admin, superusuario, unico alvo, jamais propria conta.
        if not request.user.is_active or not request.user.is_superuser or not self.has_delete_permission(request):
            raise PermissionDenied
        if queryset.count() != 1:
            self.message_user(request, "Selecione exatamente um usuario para exclusao definitiva.", messages.ERROR)
            return None

        target = queryset.first()
        if target.pk == request.user.pk or target.is_superuser or target.is_staff:
            self.message_user(request, "Nao e permitido excluir definitivamente a propria conta ou contas administrativas.", messages.ERROR)
            return None

        # Usa o coletor real de exclusao do Django, nao a simulacao do soft delete.
        deleted_objects, model_count, perms_needed, protected = get_deleted_objects(
            [target], request, self.admin_site
        )
        if protected or perms_needed:
            self.message_user(
                request,
                "Exclusao bloqueada: existem relacionamentos protegidos ou permissoes insuficientes. "
                "Use a desativacao (soft delete).",
                messages.ERROR,
            )
            return None

        if request.POST.get("confirm_hard_delete") == "EXCLUIR DEFINITIVAMENTE":
            try:
                with transaction.atomic():
                    # A exclusao em cascata ocorre apenas para relacionamentos CASCADE.
                    target.delete()
            except (ProtectedError, RestrictedError):
                self.message_user(request, "Exclusao bloqueada por registros vinculados.", messages.ERROR)
                return None
            self.message_user(request, f"Usuario {target.username} excluido definitivamente.", messages.SUCCESS)
            return None

        context = {
            **self.admin_site.each_context(request),
            "title": "Confirmar exclusao definitiva de usuario",
            "opts": self.model._meta,
            "usuario": target,
            "deleted_objects": deleted_objects,
            "model_count": model_count,
            "action_checkbox_name": ACTION_CHECKBOX_NAME,
            "action_name": "hard_delete_user",
        }
        return TemplateResponse(request, "admin/accounts/user/confirm_hard_delete.html", context)

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

class HubModuleAdminForm(forms.ModelForm):
    class Meta:
        model = HubModule
        fields = "__all__"
        widgets = {
            "icon_color": forms.TextInput(
                attrs={
                    "type": "color",
                    "style": "width: 72px; height: 40px; padding: 2px;",
                }
            )
        }


@admin.register(HubModule)
class HubModuleAdmin(admin.ModelAdmin):
    form = HubModuleAdminForm
    list_display = [
        "name",
        "slug",
        "route",
        "icon_color_preview",
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

    @admin.display(description="Cor", ordering="icon_color")
    def icon_color_preview(self, obj):
        return format_html(
            '<span style="display:inline-block;width:22px;height:22px;'
            'border-radius:6px;border:1px solid #777;background:{};" '
            'title="{}"></span>',
            obj.icon_color,
            obj.icon_color,
        )


@admin.register(HubMenuItem)
class HubMenuItemAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "name",
        "module",
        "parent",
        "route",
        "permission_codes",
        "favoritable",
        "desktop_enabled",
        "mobile_enabled",
        "legacy_enabled",
        "is_active",
        "order",
    ]

    list_filter = [
        "module",
        "favoritable",
        "desktop_enabled",
        "mobile_enabled",
        "legacy_enabled",
        "is_active",
    ]

    search_fields = [
        "name",
        "slug",
        "route",
        "module__name",
        "module__slug",
        "permissions__code",
    ]

    autocomplete_fields = [
        "module",
        "parent",
        "permissions",
    ]

    ordering = [
        "module__order",
        "module__name",
        "order",
        "name",
    ]

    readonly_fields = [
        "created_at",
        "updated_at",
    ]

    @admin.display(description="Permissões")
    def permission_codes(self, obj):
        codes = obj.permissions.order_by("code").values_list(
            "code",
            flat=True,
        )
        return ", ".join(codes) or "Herda do módulo"


@admin.register(UserHubMenuItemFavorite)
class UserHubMenuItemFavoriteAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "menu_item",
        "module_name",
        "order",
        "created_at",
    ]

    list_filter = [
        "menu_item__module",
        "created_at",
    ]

    search_fields = [
        "user__username",
        "user__name",
        "user__email",
        "menu_item__name",
        "menu_item__slug",
        "menu_item__module__name",
    ]

    autocomplete_fields = [
        "user",
        "menu_item",
    ]

    ordering = [
        "user__name",
        "order",
        "menu_item__module__order",
        "menu_item__order",
        "menu_item__name",
    ]

    readonly_fields = [
        "created_at",
    ]

    @admin.display(
        description="Módulo",
        ordering="menu_item__module__name",
    )
    def module_name(self, obj):
        return obj.menu_item.module.name
