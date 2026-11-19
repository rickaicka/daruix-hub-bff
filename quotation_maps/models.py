from django.db import models


class Supplier(models.Model):
    """Cadastro comercial importado do Access, independente de conta de acesso."""

    portal_profile = models.OneToOneField(
        "accounts.Supplier", null=True, blank=True, on_delete=models.SET_NULL, related_name="quotation_supplier",
    )
    trade_name = models.TextField(blank=True)
    business_segment = models.TextField(blank=True)
    website = models.TextField(blank=True)
    payment_terms = models.TextField(blank=True)
    delivery_terms = models.TextField(blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    source_key = models.CharField(max_length=255, unique=True)
    name = models.TextField()
    document = models.TextField(blank=True)
    contact = models.TextField(blank=True)
    phone = models.TextField(blank=True)
    email = models.TextField(blank=True)
    fax = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    source = models.JSONField(default=dict)
    # Pontuação manual de condições de pagamento: 0 a 5. Entregas serão medidas pelas OCs.
    payment_score = models.PositiveSmallIntegerField(null=True, blank=True)


class QuotationMap(models.Model):
    class Status(models.TextChoices):
        READY = "READY", "Pronto para cotar"
        DRAFT = "DRAFT", "Em cotação"
        FINAL = "FINAL", "Finalizado"
        ORDERED = "ORDERED", "Ordens geradas"
        CANCELLED = "CANCELLED", "Cancelado"

    requisition = models.OneToOneField("material_requisitions.MaterialRequisition", on_delete=models.PROTECT)
    approved_revision = models.ForeignKey("material_requisitions.MaterialRequisitionRevision", on_delete=models.PROTECT)
    revision_number = models.PositiveIntegerField(default=0)
    tender_opened_at = models.DateTimeField(null=True, blank=True)
    tender_closed_at = models.DateTimeField(null=True, blank=True)
    tender_deadline = models.DateTimeField(null=True, blank=True)
    code = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.READY, db_index=True)
    version = models.PositiveIntegerField(default=1)
    items = models.JSONField(default=list)
    quotes = models.JSONField(default=list)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    buyer = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="quotation_maps_bought")


class PurchaseOrder(models.Model):
    # Identificador comercial exclusivo do Hub; não equivale à sequência legada.
    code = models.CharField(max_length=40, unique=True)
    quotation_map = models.ForeignKey(QuotationMap, on_delete=models.PROTECT, related_name="orders")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    supplier_snapshot = models.JSONField()
    lines = models.JSONField()
    terms = models.JSONField()
    total = models.DecimalField(max_digits=34, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    promised_delivery_at = models.DateField(null=True, blank=True)
    delivered_at = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["quotation_map", "supplier"], name="unique_order_per_map_supplier"),
        ]


class TenderBid(models.Model):
    quotation = models.ForeignKey(QuotationMap, on_delete=models.PROTECT, related_name="tender_bids")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    offer = models.JSONField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    # Um convite/credencial por mapa e fornecedor, sem alterar a senha permanente do Hub.
    temp_username = models.CharField(max_length=120, blank=True, db_index=True)
    temp_password_hash = models.CharField(max_length=128, blank=True)
    invitation_token_hash = models.CharField(max_length=64, blank=True, db_index=True)
    access_token_hash = models.CharField(max_length=64, blank=True, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    invited_at = models.DateTimeField(null=True, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)
    email_error = models.TextField(blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["quotation", "supplier"], name="unique_tender_bid_per_supplier"),
        ]


class TenderOutcomeNotification(models.Model):
    """Registro idempotente do agradecimento a fornecedor participante não contemplado."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendente"
        SENDING = "SENDING", "Enviando"
        SENT = "SENT", "Enviado"
        FAILED = "FAILED", "Falha"

    quotation = models.ForeignKey(QuotationMap, on_delete=models.PROTECT, related_name="outcome_notifications")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    recipient_email = models.EmailField(max_length=254)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["quotation", "supplier"], name="unique_tender_outcome_notification"),
        ]
