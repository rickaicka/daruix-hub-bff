from django.db import models


class Permission(models.Model):
    id = models.BigAutoField(
        primary_key=True,
        db_column="id_permissao",
    )

    code = models.CharField(
        max_length=100,
        unique=True,
        db_column="codigo",
        help_text="Example: proposal.view, proposal.create, purchase_order.approve",
    )

    description = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_column="descricao",
    )

    module = models.CharField(
        max_length=50,
        db_column="modulo",
        help_text="Example: proposal, purchase_order, shipment_memo, rental",
    )

    is_active = models.BooleanField(
        default=True,
        db_column="ativo",
    )

    class Meta:
        db_table = "permissoes"
        verbose_name = "Permission"
        verbose_name_plural = "Permissions"
        ordering = ["module", "code"]

    def __str__(self):
        return self.code


class GroupPermission(models.Model):
    id = models.BigAutoField(
        primary_key=True,
        db_column="id_grupo_permissao",
    )

    group = models.ForeignKey(
        "accounts.UserGroup",
        on_delete=models.CASCADE,
        db_column="id_grupo",
        related_name="group_permissions",
    )

    permission = models.ForeignKey(
        "accounts.Permission",
        on_delete=models.CASCADE,
        db_column="id_permissao",
        related_name="group_permissions",
    )

    is_active = models.BooleanField(
        default=True,
        db_column="ativo",
    )

    class Meta:
        db_table = "grupo_permissoes"
        verbose_name = "Group permission"
        verbose_name_plural = "Group permissions"
        ordering = ["group", "permission"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "permission"],
                name="uq_group_permission",
            )
        ]

    def __str__(self):
        return f"{self.group} -> {self.permission}"