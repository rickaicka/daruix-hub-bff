from django.core.exceptions import ValidationError
from django.db import models

from accounts.models.hub_module import HubModule
from accounts.models.permission import Permission


class HubMenuItem(models.Model):
    module = models.ForeignKey(
        HubModule,
        on_delete=models.CASCADE,
        related_name="menu_items",
        verbose_name="Módulo",
    )

    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="children",
        null=True,
        blank=True,
        verbose_name="Item pai",
        help_text="Use para agrupar funcionalidades dentro do mesmo módulo.",
    )

    name = models.CharField(
        max_length=120,
        verbose_name="Nome",
    )

    slug = models.SlugField(
        max_length=140,
        unique=True,
        verbose_name="Slug",
    )

    route = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Rota",
        help_text=(
            "Rota usada pelo Hub Shell. Pode ficar vazia em itens usados apenas "
            "como agrupadores."
        ),
    )

    icon = models.CharField(
        max_length=80,
        blank=True,
        default="",
        verbose_name="Ícone",
    )

    permissions = models.ManyToManyField(
        Permission,
        related_name="hub_menu_items",
        blank=True,
        verbose_name="Permissões de acesso",
        help_text=(
            "A funcionalidade fica visível quando o usuário possui pelo menos "
            "uma das permissões selecionadas. Sem permissões, herda o acesso "
            "do módulo."
        ),
    )

    favoritable = models.BooleanField(
        default=True,
        verbose_name="Pode ser favoritado",
    )

    desktop_enabled = models.BooleanField(
        default=True,
        verbose_name="Disponível no desktop",
    )

    mobile_enabled = models.BooleanField(
        default=True,
        verbose_name="Disponível no mobile",
    )

    legacy_enabled = models.BooleanField(
        default=False,
        verbose_name="É legado",
    )

    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Ordem",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Ativo",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Criado em",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Atualizado em",
    )

    class Meta:
        db_table = "hub_itens_menu"
        verbose_name = "Funcionalidade do Hub"
        verbose_name_plural = "Funcionalidades do Hub"
        ordering = ["module__order", "module__name", "order", "name"]
        indexes = [
            models.Index(
                fields=["module", "parent", "is_active", "order"],
                name="hub_item_menu_tree_idx",
            )
        ]

    def clean(self):
        errors = {}

        if self.parent_id:
            if self.pk and self.parent_id == self.pk:
                errors["parent"] = "Uma funcionalidade não pode ser pai dela mesma."
            elif self.parent.module_id != self.module_id:
                errors["parent"] = (
                    "O item pai deve pertencer ao mesmo módulo da funcionalidade."
                )
            elif self.pk:
                ancestor = self.parent
                visited_ids = set()

                while ancestor:
                    if ancestor.pk == self.pk:
                        errors["parent"] = (
                            "A hierarquia informada cria um ciclo entre funcionalidades."
                        )
                        break

                    if ancestor.pk in visited_ids:
                        break

                    visited_ids.add(ancestor.pk)
                    ancestor = ancestor.parent

        if self.favoritable and not self.route.strip():
            errors["favoritable"] = (
                "Somente funcionalidades com rota podem ser favoritadas."
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.module.name} - {self.name}"


