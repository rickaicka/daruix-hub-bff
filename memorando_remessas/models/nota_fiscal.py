from django.db import models


class ShipmentMemoInvoice(models.Model):
    """Nota fiscal recebida, vinculada a um memorando."""
    memo = models.ForeignKey('memorando_remessas.ShipmentMemo', on_delete=models.CASCADE, related_name='invoices')
    number = models.CharField(max_length=30)
    series = models.CharField(max_length=12, blank=True, default='')
    issuer_name = models.CharField(max_length=255, blank=True, default='')
    trade_name = models.CharField(max_length=255, blank=True, default='')
    issuer_document = models.CharField(max_length=20, blank=True, default='')
    total_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    access_key = models.CharField(max_length=50, blank=True, default='')
    description = models.CharField(max_length=255, blank=True, default='')
    source = models.CharField(max_length=16, default='MANUAL')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
