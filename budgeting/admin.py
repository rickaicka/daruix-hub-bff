from django.contrib import admin

from .choices import DataOrigin
from .models import (
    LegacyImportRun,
    MaterialGroup,
    ServiceComposition,
    ServiceCompositionItem,
    ServiceCompositionVersion,
    Supply,
    UnitMeasure,
)


def concrete_field_names(model) -> tuple[str, ...]:
    return tuple(field.name for field in model._meta.fields)


class NoDirectMutationAdminMixin:
    actions = None

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Supply)
class SupplyAdmin(admin.ModelAdmin):
    list_display = (
        "description",
        "supply_type",
        "unit",
        "origin",
        "is_active",
    )
    list_filter = ("origin", "supply_type", "is_active")
    search_fields = (
        "description",
        "full_description",
        "legacy_id",
    )
    readonly_fields = (
        "origin",
        "legacy_table",
        "legacy_id",
        "legacy_payload",
        "legacy_payload_hash",
        "imported_at",
        "created_at",
        "updated_at",
    )

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and obj.origin == DataOrigin.LEGACY:
            return concrete_field_names(Supply)

        return super().get_readonly_fields(request, obj)

    def has_delete_permission(self, request, obj=None) -> bool:
        if not super().has_delete_permission(request, obj):
            return False

        return obj is None or obj.origin != DataOrigin.LEGACY

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions


class VersionInline(admin.TabularInline):
    model = ServiceCompositionVersion
    extra = 0
    show_change_link = True
    fields = ("number", "status", "origin", "unit", "total")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(ServiceComposition)
class ServiceCompositionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "origin", "is_active")
    list_filter = ("origin", "is_active")
    search_fields = ("name", "code", "legacy_id")
    readonly_fields = (
        "origin",
        "legacy_table",
        "legacy_id",
        "created_at",
        "updated_at",
    )
    inlines = (VersionInline,)

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and obj.origin == DataOrigin.LEGACY:
            return concrete_field_names(ServiceComposition)

        return super().get_readonly_fields(request, obj)

    def has_delete_permission(self, request, obj=None) -> bool:
        if not super().has_delete_permission(request, obj):
            return False

        return obj is None or obj.origin != DataOrigin.LEGACY

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions


class ItemInline(admin.TabularInline):
    model = ServiceCompositionItem
    extra = 0
    can_delete = False
    fields = concrete_field_names(ServiceCompositionItem)
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(ServiceCompositionVersion)
class ServiceCompositionVersionAdmin(NoDirectMutationAdminMixin, admin.ModelAdmin):
    list_display = ("composition", "number", "status", "origin", "total")
    list_filter = ("status", "origin")
    search_fields = ("composition__name", "composition__code")
    readonly_fields = concrete_field_names(ServiceCompositionVersion)
    inlines = (ItemInline,)


@admin.register(LegacyImportRun)
class LegacyImportRunAdmin(NoDirectMutationAdminMixin, admin.ModelAdmin):
    list_display = (
        "resource",
        "initial",
        "status",
        "started_at",
        "finished_at",
    )
    list_filter = ("resource", "status", "initial")
    readonly_fields = concrete_field_names(LegacyImportRun)


@admin.register(UnitMeasure)
class UnitMeasureAdmin(NoDirectMutationAdminMixin, admin.ModelAdmin):
    list_display = ("legacy_id", "sigla", "nome", "ativo")
    list_filter = ("ativo",)
    search_fields = ("sigla", "nome", "legacy_id")
    readonly_fields = concrete_field_names(UnitMeasure)


@admin.register(MaterialGroup)
class MaterialGroupAdmin(NoDirectMutationAdminMixin, admin.ModelAdmin):
    list_display = ("legacy_id", "nome", "ativo")
    list_filter = ("ativo",)
    search_fields = ("nome", "legacy_id")
    readonly_fields = concrete_field_names(MaterialGroup)
