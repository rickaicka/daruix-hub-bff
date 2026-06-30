from django.db import models

from accounts._old.models.user_type import UserType


class HubModule(models.Model):
    """
    Módulo/funcionalidade visível no Hub.

    Exemplos:
    - dashboard
    - purchase_orders
    - deductibles
    - admin
    """

    user_type = models.ForeignKey(
        UserType,
        on_delete=models.CASCADE,
        related_name="modules",
    )

    slug = models.SlugField()
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    route = models.CharField(max_length=150)
    icon = models.CharField(max_length=80, blank=True)

    desktop_enabled = models.BooleanField(default=True)
    mobile_enabled = models.BooleanField(default=True)
    legacy_enabled = models.BooleanField(default=False)

    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    legacy_object_name = models.CharField(max_length=150, blank=True)

    class Meta:
        unique_together = ("user_type", "slug")
        ordering = ["order", "name"]
        verbose_name = "Módulo do Hub"
        verbose_name_plural = "Módulos do Hub"

    def __str__(self):
        return f"{self.user_type.name} / {self.name}"