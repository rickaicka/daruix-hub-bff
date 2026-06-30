from django.db import models

from accounts._old.models.hub_module import HubModule
from accounts._old.models.user_group import UserGroup


class PermissionCode(models.Model):
    """
    Permissão padronizada do novo Hub.

    Formato recomendado:
    <tipo>.<modulo>.<acao>

    Exemplos:
    - employee.purchase_orders.view
    - employee.purchase_orders.create
    - client.dashboard.view
    """

    module = models.ForeignKey(
        HubModule,
        on_delete=models.CASCADE,
        related_name="permissions",
    )

    code = models.CharField(max_length=150, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    legacy_permission_name = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["module__name", "code"]
        verbose_name = "Permissão"
        verbose_name_plural = "Permissões"

    def __str__(self):
        return self.code


class GroupPermission(models.Model):
    """
    Permissões herdadas por grupo.

    Exemplo:
    Grupo Colaborador/Diretoria recebe:
    - employee.purchase_orders.view
    - employee.purchase_orders.approve
    """

    group = models.ForeignKey(
        UserGroup,
        on_delete=models.CASCADE,
        related_name="group_permissions",
    )

    permission = models.ForeignKey(
        PermissionCode,
        on_delete=models.CASCADE,
        related_name="group_permissions",
    )

    class Meta:
        unique_together = ("group", "permission")
        verbose_name = "Permissão do grupo"
        verbose_name_plural = "Permissões dos grupos"

    def __str__(self):
        return f"{self.group} - {self.permission}"