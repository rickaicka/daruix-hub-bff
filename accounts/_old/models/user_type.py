from django.db import models


class UserType(models.Model):
    """
    Tipo principal de usuário no Daruix Hub.

    Exemplos:
    - client       = Cliente
    - supplier     = Fornecedor
    - employee     = Colaborador
    """

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)

    legacy_id = models.IntegerField(null=True, blank=True)
    legacy_name = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Tipo de usuário"
        verbose_name_plural = "Tipos de usuários"

    def __str__(self):
        return self.name