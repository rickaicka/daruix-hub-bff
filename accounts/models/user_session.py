import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class UserSession(models.Model):
    class EndReason(models.TextChoices):
        LOGOUT = "logout", "Logout"
        IDLE = "idle", "Inatividade"
        END_OF_DAY = "end_of_day", "Fim do dia"
        REPLACED = "replaced", "Substituída"
        INVALID = "invalid", "Inválida"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="hub_sessions",
    )

    refresh_jti = models.CharField(
        max_length=255,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    last_activity_at = models.DateTimeField(
        default=timezone.now,
    )

    expires_at = models.DateTimeField()

    is_active = models.BooleanField(
        default=True,
    )

    ended_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    end_reason = models.CharField(
        max_length=30,
        choices=EndReason.choices,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "user_sessions"
        ordering = ["-created_at"]

    def close(self, reason: str):
        if not self.is_active:
            return

        self.is_active = False
        self.ended_at = timezone.now()
        self.end_reason = reason

        self.save(
            update_fields=[
                "is_active",
                "ended_at",
                "end_reason",
            ]
        )

    def __str__(self):
        return f"{self.user} - {self.id}"