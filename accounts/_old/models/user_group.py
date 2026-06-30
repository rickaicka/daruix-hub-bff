from django.db import models

from accounts._old.models.user_type import UserType


class UserGroup(models.Model):
    """
    Grupo do usuário dentro de um tipo.

    Exemplos:
    - Cliente / Diretoria
    - Cliente / Operacional
    - Fornecedor / Diretoria
    - Colaborador / Compras
    - Colaborador / Engenharia
    """

    user_type = models.ForeignKey(
        UserType,
        on_delete=models.CASCADE,
        related_name="groups",
    )

    slug = models.SlugField()
    name = models.CharField(max_length=100)

    legacy_id = models.IntegerField(null=True, blank=True)
    legacy_name = models.CharField(max_length=100, blank=True)

    class Meta:
        unique_together = ("user_type", "slug")
        ordering = ["user_type__name", "name"]
        verbose_name = "Grupo de usuário"
        verbose_name_plural = "Grupos de usuários"

    def __str__(self):
        return f"{self.user_type.name} / {self.name}"