from django.conf import settings
from django.db import models


class HubNotification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='hub_notifications')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    key = models.CharField(max_length=160)
    kind = models.CharField(max_length=48)
    title = models.CharField(max_length=180)
    message = models.TextField(blank=True)
    route = models.CharField(max_length=500, blank=True)
    module = models.CharField(max_length=64, blank=True, db_index=True)
    event = models.CharField(max_length=100, blank=True, db_index=True)
    resource_type = models.CharField(max_length=100, blank=True)
    resource_id = models.CharField(max_length=100, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-id')
        constraints = [models.UniqueConstraint(fields=['recipient', 'key'], name='uniq_hub_notice_recipient_key')]
