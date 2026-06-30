from django.db import models

from accounts.models.permission import Permission


class HubModule(models.Model):
    name = models.CharField(
        max_length=120,
        verbose_name="Nome",
    )

    slug = models.SlugField(
        max_length=120,
        unique=True,
        verbose_name="Slug",
    )

    route = models.CharField(
        max_length=150,
        verbose_name="Rota",
        help_text="Rota usada pelo Hub Shell. Exemplo: /financeiro",
    )

    icon = models.CharField(
        max_length=80,
        blank=True,
        default="",
        verbose_name="Ícone",
        help_text="Nome do ícone usado no front. Exemplo: dashboard, payments, engineering.",
    )

    permission = models.ForeignKey(
        Permission,
        on_delete=models.PROTECT,
        related_name="hub_modules",
        verbose_name="Permissão mínima de acesso",
    )

    desktop_enabled = models.BooleanField(
        default=True,
        verbose_name="Disponível no desktop",
    )

    mobile_enabled = models.BooleanField(
        default=True,
        verbose_name="Disponível no mobile",
    )

    mfe_enabled = models.BooleanField(
        default=False,
        verbose_name="É MFE",
    )

    legacy_enabled = models.BooleanField(
        default=False,
        verbose_name="É legado",
    )

    remote_name = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="Remote name",
        help_text="Nome do remote no Module Federation. Exemplo: financeiro",
    )

    remote_entry = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Remote entry",
        help_text="URL do remoteEntry.js. Exemplo: http://localhost:4304/remoteEntry.js",
    )

    exposed_module = models.CharField(
        max_length=120,
        blank=True,
        default="./Routes",
        verbose_name="Exposed module",
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
        db_table = "hub_modulos"
        verbose_name = "Módulo do Hub"
        verbose_name_plural = "Módulos do Hub"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name