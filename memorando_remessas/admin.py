from django.contrib import admin
from django.utils.html import format_html

from memorando_remessas.models import (
    ShipmentMemo,
    ShipmentMemoFile,
    ShipmentMemoHistory,
    ShipmentMemoOption,
    ShipmentMemoOptionSelection,
    ShipmentMemoResponsible,
    ShipmentMemoSequence,
)


class ShipmentMemoResponsibleInline(admin.TabularInline):
    model = ShipmentMemoResponsible
    extra = 0

    fields = [
        "user",
        "is_primary",
        "added_by",
        "created_at",
    ]

    raw_id_fields = [
        "user",
        "added_by",
    ]

    readonly_fields = [
        "created_at",
    ]

    show_change_link = True


class ShipmentMemoOptionSelectionInline(admin.TabularInline):
    model = ShipmentMemoOptionSelection
    extra = 0

    fields = [
        "option",
        "selected_by",
        "created_at",
    ]

    raw_id_fields = [
        "option",
        "selected_by",
    ]

    readonly_fields = [
        "created_at",
    ]

    show_change_link = True


class ShipmentMemoFileInline(admin.TabularInline):
    model = ShipmentMemoFile
    extra = 0
    can_delete = False

    fields = [
        "original_name",
        "content_type",
        "formatted_size",
        "uploaded_by",
        "created_at",
    ]

    readonly_fields = [
        "original_name",
        "content_type",
        "formatted_size",
        "uploaded_by",
        "created_at",
    ]

    show_change_link = True

    @admin.display(
        description="Tamanho",
    )
    def formatted_size(self, obj):
        if not obj or obj.size is None:
            return "-"

        return self._format_file_size(
            obj.size
        )

    @staticmethod
    def _format_file_size(size):
        size = int(size or 0)

        if size < 1024:
            return f"{size} B"

        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"

        if size < 1024 * 1024 * 1024:
            return (
                f"{size / (1024 * 1024):.1f} MB"
            )

        return (
            f"{size / (1024 * 1024 * 1024):.1f} GB"
        )

    def has_add_permission(
        self,
        request,
        obj=None,
    ):
        return False


class ShipmentMemoHistoryInline(admin.TabularInline):
    model = ShipmentMemoHistory
    extra = 0
    can_delete = False

    fields = [
        "action",
        "actor",
        "description",
        "created_at",
    ]

    readonly_fields = [
        "action",
        "actor",
        "description",
        "created_at",
    ]

    show_change_link = True

    ordering = [
        "-created_at",
        "-id",
    ]

    def has_add_permission(
        self,
        request,
        obj=None,
    ):
        return False


@admin.register(ShipmentMemo)
class ShipmentMemoAdmin(admin.ModelAdmin):
    list_display = [
        "code",
        "work_name",
        "cost_center",
        "client_name",
        "status",
        "revision",
        "shipping_date",
        "primary_responsible",
        "created_by",
        "created_at",
    ]

    list_filter = [
        "status",
        "work_source",
        "revision",
        "shipping_date",
        "created_at",
        "updated_at",
    ]

    search_fields = [
        "code",
        "sequence_number",
        "work_name",
        "cost_center",
        "client_name",
        "client_document",
        "subject",
        "attention_to",
        "responsible_links__user__name",
        "responsible_links__user__username",
        "responsible_links__user__email",
    ]

    ordering = [
        "-created_at",
        "-id",
    ]

    date_hierarchy = "created_at"

    list_select_related = [
        "revised_from",
        "created_by",
        "updated_by",
        "sent_by",
        "cancelled_by",
    ]

    raw_id_fields = [
        "revised_from",
        "created_by",
        "updated_by",
        "sent_by",
        "cancelled_by",
    ]

    readonly_fields = [
        "code",
        "sequence_number",
        "created_at",
        "updated_at",
    ]

    fieldsets = [
        (
            "Identificação",
            {
                "fields": [
                    "code",
                    "sequence_number",
                    "revision",
                    "revised_from",
                    "status",
                ],
            },
        ),
        (
            "Obra e cliente",
            {
                "fields": [
                    "work_source",
                    "legacy_work_id",
                    "legacy_proposal_id",
                    "cost_center",
                    "work_name",
                    "client_name",
                    "client_document",
                ],
            },
        ),
        (
            "Dados do memorando",
            {
                "fields": [
                    "shipping_date",
                    "subject",
                    "attention_to",
                    "notes",
                ],
            },
        ),
        (
            "Criação e atualização",
            {
                "fields": [
                    "created_by",
                    "updated_by",
                    "created_at",
                    "updated_at",
                ],
            },
        ),
        (
            "Envio",
            {
                "fields": [
                    "sent_by",
                    "sent_at",
                ],
                "classes": [
                    "collapse",
                ],
            },
        ),
        (
            "Cancelamento",
            {
                "fields": [
                    "cancelled_by",
                    "cancelled_at",
                    "cancellation_reason",
                ],
                "classes": [
                    "collapse",
                ],
            },
        ),
    ]

    inlines = [
        ShipmentMemoResponsibleInline,
        ShipmentMemoOptionSelectionInline,
        ShipmentMemoFileInline,
        ShipmentMemoHistoryInline,
    ]

    @admin.display(
        description="Responsável principal",
        ordering="responsible_links__user__name",
    )
    def primary_responsible(self, obj):
        responsible = (
            obj.responsible_links
            .filter(is_primary=True)
            .select_related("user")
            .first()
        )

        if not responsible:
            return "-"

        return (
            responsible.user.name
            or responsible.user.username
        )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "revised_from",
                "created_by",
                "updated_by",
                "sent_by",
                "cancelled_by",
            )
            .prefetch_related(
                "responsible_links__user",
            )
            .distinct()
        )


@admin.register(ShipmentMemoResponsible)
class ShipmentMemoResponsibleAdmin(admin.ModelAdmin):
    list_display = [
        "shipment_memo",
        "user",
        "is_primary",
        "added_by",
        "created_at",
    ]

    list_filter = [
        "is_primary",
        "created_at",
    ]

    search_fields = [
        "shipment_memo__code",
        "shipment_memo__work_name",
        "shipment_memo__cost_center",
        "user__name",
        "user__username",
        "user__email",
        "added_by__name",
        "added_by__username",
        "added_by__email",
    ]

    ordering = [
        "-created_at",
        "-id",
    ]

    list_select_related = [
        "shipment_memo",
        "user",
        "added_by",
    ]

    raw_id_fields = [
        "shipment_memo",
        "user",
        "added_by",
    ]

    readonly_fields = [
        "created_at",
    ]

    date_hierarchy = "created_at"


@admin.register(ShipmentMemoOption)
class ShipmentMemoOptionAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "option_type",
        "code",
        "order",
        "is_active",
        "updated_at",
    ]

    list_editable = [
        "order",
        "is_active",
    ]

    list_filter = [
        "option_type",
        "is_active",
        "created_at",
        "updated_at",
    ]

    search_fields = [
        "name",
        "code",
        "description",
    ]

    ordering = [
        "option_type",
        "order",
        "name",
        "id",
    ]

    readonly_fields = [
        "created_at",
        "updated_at",
    ]

    fieldsets = [
        (
            "Identificação",
            {
                "fields": [
                    "option_type",
                    "code",
                    "name",
                ],
            },
        ),
        (
            "Configuração",
            {
                "fields": [
                    "description",
                    "order",
                    "is_active",
                ],
            },
        ),
        (
            "Auditoria",
            {
                "fields": [
                    "created_at",
                    "updated_at",
                ],
                "classes": [
                    "collapse",
                ],
            },
        ),
    ]


@admin.register(ShipmentMemoOptionSelection)
class ShipmentMemoOptionSelectionAdmin(
    admin.ModelAdmin
):
    list_display = [
        "shipment_memo",
        "option",
        "option_type",
        "selected_by",
        "created_at",
    ]

    list_filter = [
        "option__option_type",
        "created_at",
    ]

    search_fields = [
        "shipment_memo__code",
        "shipment_memo__work_name",
        "shipment_memo__cost_center",
        "option__name",
        "option__code",
        "selected_by__name",
        "selected_by__username",
        "selected_by__email",
    ]

    ordering = [
        "-created_at",
        "-id",
    ]

    list_select_related = [
        "shipment_memo",
        "option",
        "selected_by",
    ]

    raw_id_fields = [
        "shipment_memo",
        "option",
        "selected_by",
    ]

    readonly_fields = [
        "created_at",
    ]

    date_hierarchy = "created_at"

    @admin.display(
        description="Tipo",
        ordering="option__option_type",
    )
    def option_type(self, obj):
        return obj.option.get_option_type_display()


@admin.register(ShipmentMemoFile)
class ShipmentMemoFileAdmin(admin.ModelAdmin):
    list_display = [
        "original_name",
        "shipment_memo",
        "content_type",
        "formatted_size",
        "uploaded_by",
        "created_at",
        "file_exists",
    ]

    list_filter = [
        "content_type",
        "created_at",
    ]

    search_fields = [
        "original_name",
        "shipment_memo__code",
        "shipment_memo__work_name",
        "shipment_memo__cost_center",
        "uploaded_by__name",
        "uploaded_by__username",
        "uploaded_by__email",
    ]

    ordering = [
        "-created_at",
        "-id",
    ]

    list_select_related = [
        "shipment_memo",
        "uploaded_by",
    ]

    raw_id_fields = [
        "shipment_memo",
        "uploaded_by",
    ]

    readonly_fields = [
        "shipment_memo",
        "file",
        "file_link",
        "original_name",
        "content_type",
        "formatted_size",
        "uploaded_by",
        "created_at",
    ]

    fieldsets = [
        (
            "Memorando",
            {
                "fields": [
                    "shipment_memo",
                ],
            },
        ),
        (
            "Arquivo",
            {
                "fields": [
                    "original_name",
                    "file",
                    "file_link",
                    "content_type",
                    "formatted_size",
                ],
            },
        ),
        (
            "Upload",
            {
                "fields": [
                    "uploaded_by",
                    "created_at",
                ],
            },
        ),
    ]

    date_hierarchy = "created_at"

    @admin.display(
        description="Tamanho",
        ordering="size",
    )
    def formatted_size(self, obj):
        size = int(obj.size or 0)

        if size < 1024:
            return f"{size} B"

        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"

        if size < 1024 * 1024 * 1024:
            return (
                f"{size / (1024 * 1024):.1f} MB"
            )

        return (
            f"{size / (1024 * 1024 * 1024):.1f} GB"
        )

    @admin.display(
        description="Disponível",
        boolean=True,
    )
    def file_exists(self, obj):
        if not obj.file or not obj.file.name:
            return False

        try:
            return obj.file.storage.exists(
                obj.file.name
            )
        except OSError:
            return False

    @admin.display(
        description="Arquivo armazenado",
    )
    def file_link(self, obj):
        if not obj.file or not obj.file.name:
            return "-"

        try:
            exists = obj.file.storage.exists(
                obj.file.name
            )
        except OSError:
            exists = False

        if not exists:
            return "Arquivo físico não encontrado."

        try:
            url = obj.file.url
        except (NotImplementedError, ValueError):
            return obj.file.name

        return format_html(
            '<a href="{}" target="_blank" '
            'rel="noopener noreferrer">{}</a>',
            url,
            obj.original_name,
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(
        self,
        request,
        obj=None,
    ):
        return False

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return False


@admin.register(ShipmentMemoHistory)
class ShipmentMemoHistoryAdmin(admin.ModelAdmin):
    list_display = [
        "shipment_memo",
        "action",
        "actor",
        "description_summary",
        "created_at",
    ]

    list_filter = [
        "action",
        "created_at",
    ]

    search_fields = [
        "shipment_memo__code",
        "shipment_memo__work_name",
        "shipment_memo__cost_center",
        "actor__name",
        "actor__username",
        "actor__email",
        "description",
    ]

    ordering = [
        "-created_at",
        "-id",
    ]

    list_select_related = [
        "shipment_memo",
        "actor",
    ]

    raw_id_fields = [
        "shipment_memo",
        "actor",
    ]

    readonly_fields = [
        "shipment_memo",
        "action",
        "actor",
        "description",
        "before_data",
        "after_data",
        "metadata",
        "created_at",
    ]

    fieldsets = [
        (
            "Ação",
            {
                "fields": [
                    "shipment_memo",
                    "action",
                    "actor",
                    "description",
                    "created_at",
                ],
            },
        ),
        (
            "Dados da alteração",
            {
                "fields": [
                    "before_data",
                    "after_data",
                    "metadata",
                ],
                "classes": [
                    "collapse",
                ],
            },
        ),
    ]

    date_hierarchy = "created_at"

    @admin.display(
        description="Descrição",
    )
    def description_summary(self, obj):
        description = (
            obj.description or ""
        ).strip()

        if not description:
            return "-"

        if len(description) <= 80:
            return description

        return f"{description[:77]}..."

    def has_add_permission(self, request):
        return False

    def has_change_permission(
        self,
        request,
        obj=None,
    ):
        return False

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return False


@admin.register(ShipmentMemoSequence)
class ShipmentMemoSequenceAdmin(admin.ModelAdmin):
    list_display = [
        "key",
        "current_value",
        "updated_at",
    ]

    search_fields = [
        "key",
    ]

    ordering = [
        "key",
    ]

    readonly_fields = [
        "key",
        "current_value",
        "updated_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(
        self,
        request,
        obj=None,
    ):
        return False

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return False