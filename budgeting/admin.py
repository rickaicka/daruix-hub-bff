from django.contrib import admin

from .models import (
    LegacyImportRun,
    ServiceComposition,
    ServiceCompositionItem,
    ServiceCompositionVersion,
    Supply,
)


@admin.register(Supply)
class SupplyAdmin(admin.ModelAdmin):
    list_display = ("description", "code", "supply_type", "unit", "origin", "is_active")
    list_filter = ("origin", "supply_type", "is_active")
    search_fields = ("description", "code")
    readonly_fields = ("legacy_payload", "legacy_payload_hash", "imported_at")


class VersionInline(admin.TabularInline):
    model = ServiceCompositionVersion
    extra = 0
    show_change_link = True
    fields = ("number", "status", "origin", "unit", "total")
    readonly_fields = fields
    can_delete = False


@admin.register(ServiceComposition)
class ServiceCompositionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "origin", "is_active")
    list_filter = ("origin", "is_active")
    search_fields = ("name", "code")
    inlines = (VersionInline,)


class ItemInline(admin.TabularInline):
    model = ServiceCompositionItem
    extra = 0
    can_delete = False
    readonly_fields = (
        "item_type",
        "description_snapshot",
        "unit_snapshot",
        "coefficient",
        "material_unit_price",
        "labor_unit_price",
        "equipment_unit_price",
    )


@admin.register(ServiceCompositionVersion)
class ServiceCompositionVersionAdmin(admin.ModelAdmin):
    list_display = ("composition", "number", "status", "origin", "total")
    list_filter = ("status", "origin")
    inlines = (ItemInline,)


@admin.register(LegacyImportRun)
class LegacyImportRunAdmin(admin.ModelAdmin):
    list_display = ("resource", "initial", "status", "started_at", "finished_at")
    list_filter = ("resource", "status", "initial")
    readonly_fields = ("resource", "initial", "status", "started_at", "finished_at", "counters", "errors")

