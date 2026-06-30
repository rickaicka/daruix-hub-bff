from django.db import models


class LegacyMigrationLog(models.Model):
    """
    Log de migração para rastrear o que veio do Access.
    """

    entity_type = models.CharField(max_length=50)
    legacy_id = models.CharField(max_length=100)
    django_model = models.CharField(max_length=100)
    django_id = models.CharField(max_length=100)

    status = models.CharField(max_length=30)
    message = models.TextField(blank=True)

    migrated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-migrated_at"]
        verbose_name = "Log de migração legado"
        verbose_name_plural = "Logs de migração legado"

    def __str__(self):
        return f"{self.entity_type} {self.legacy_id} - {self.status}"