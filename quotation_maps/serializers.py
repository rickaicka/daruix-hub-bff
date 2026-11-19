from rest_framework import serializers

from .composition_paths import composition_paths
from .models import PurchaseOrder, QuotationMap, Supplier


SUPPLIER_FIELDS = ("id", "name", "document", "contact", "phone", "email", "fax")


class SupplierRead(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    evaluation = serializers.SerializerMethodField()

    def get_status(self, obj):
        from .models import PurchaseOrder
        return "FORNECEDOR" if PurchaseOrder.objects.filter(supplier_id=obj.pk).exists() else "PROSPECTADOR"

    def get_evaluation(self, obj):
        from .evaluation import supplier_evaluation
        return supplier_evaluation(obj)

    class Meta:
        model = Supplier
        # Condições padrão do cadastro, usadas para preencher o comparativo.
        fields = SUPPLIER_FIELDS + ("payment_terms", "delivery_terms", "status", "evaluation")


class MapSummary(serializers.ModelSerializer):
    pc = serializers.CharField(source="requisition.proposal.code")
    work = serializers.CharField(source="requisition.proposal.work_name")
    rm = serializers.CharField(source="requisition.number")

    class Meta:
        model = QuotationMap
        fields = ("id", "code", "pc", "work", "rm", "status", "created_at")


class OrderRead(serializers.ModelSerializer):
    class Meta:
        model = PurchaseOrder
        fields = ("id", "code", "supplier_snapshot", "lines", "terms", "total", "created_at", "promised_delivery_at")


class MapRead(MapSummary):
    buyer = serializers.SerializerMethodField()

    def get_buyer(self, quotation):
        user = quotation.buyer
        return {"id": user.pk, "name": user.name or user.username} if user else None

    items = serializers.SerializerMethodField()
    orders = OrderRead(many=True, read_only=True)
    quotes = serializers.SerializerMethodField()

    def get_quotes(self, quotation):
        # Consulta atual do cadastro: atualizações posteriores podem ser
        # reaplicadas explicitamente no comparativo, sem mudar cotações fechadas.
        supplier_ids = [quote.get("supplier", {}).get("id") for quote in quotation.quotes]
        suppliers = Supplier.objects.in_bulk(supplier_ids)
        result = []
        for original in quotation.quotes:
            quote = {**original, "supplier": dict(original.get("supplier") or {})}
            supplier = suppliers.get(quote["supplier"].get("id"))
            if supplier:
                quote["supplier"].update(
                    payment_terms=supplier.payment_terms,
                    delivery_terms=supplier.delivery_terms,
                )
                # Compatibilidade para mapas criados antes desta integração:
                # preenche somente campos vazios que nunca foram alterados.
                if not quote.get("payment") and not quote.get("manual_terms_payment", False):
                    quote["payment"] = supplier.payment_terms[:255]
                if not quote.get("delivery") and not quote.get("manual_terms_delivery", False):
                    quote["delivery"] = supplier.delivery_terms[:255]
            result.append(quote)
        return result

    class Meta(MapSummary.Meta):
        fields = MapSummary.Meta.fields + ("version", "items", "quotes", "notes", "orders", "tender_opened_at", "tender_closed_at", "tender_deadline", "buyer")


    def get_items(self, quotation):
        paths = composition_paths(quotation)
        return [
            {**item, "composition_path": paths[item["id"]]} if item["id"] in paths else item
            for item in quotation.items
        ]


class VersionWrite(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


class OfferWrite(serializers.Serializer):
    item_id = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(max_digits=14, decimal_places=6, min_value=0, allow_null=True)
    # Campos antigos ainda são aceitos para compatibilidade; o portal não os apresenta.
    available_quantity = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=0, allow_null=True, default=None, required=False,
    )
    brand = serializers.CharField(max_length=255, allow_blank=True, default="", required=False)
    notes = serializers.CharField(max_length=4000, allow_blank=True, default="")
    selected = serializers.BooleanField(default=False)
    restore_tender = serializers.BooleanField(default=False, required=False)


class QuoteWrite(serializers.Serializer):
    supplier_id = serializers.IntegerField(min_value=1)
    contact = serializers.CharField(max_length=255, allow_blank=True, required=False)
    phone = serializers.CharField(max_length=255, allow_blank=True, required=False)
    email = serializers.CharField(max_length=255, allow_blank=True, required=False)
    payment = serializers.CharField(max_length=255, allow_blank=True, default="")
    delivery = serializers.CharField(max_length=255, allow_blank=True, default="")
    quoted_on = serializers.DateField(allow_null=True, default=None)
    freight = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, default=0)
    discount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, default=0)
    notes = serializers.CharField(max_length=4000, allow_blank=True, default="")
    offers = OfferWrite(many=True)


class MapWrite(VersionWrite):
    quotes = QuoteWrite(many=True, max_length=6)
    notes = serializers.CharField(max_length=4000, allow_blank=True, default="")


class SupplierWrite(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    evaluation = serializers.SerializerMethodField()

    def get_status(self, obj):
        return SupplierRead(obj).data["status"]

    def get_evaluation(self, obj):
        return SupplierRead(obj).data["evaluation"]

    def validate_payment_score(self, value):
        if value is not None and not 0 <= value <= 5:
            raise serializers.ValidationError("A nota de pagamento deve estar entre 0 e 5.")
        return value

    class Meta:
        model = Supplier
        fields = SUPPLIER_FIELDS + ("active", "address", "notes", "portal_profile", "trade_name",
                                   "business_segment", "website", "payment_terms", "delivery_terms", "payment_score", "status", "evaluation")
        read_only_fields = ("status", "evaluation")
        extra_kwargs = {"name": {"max_length": 255}}

    def validate_portal_profile(self, profile):
        if profile is not None and (
            not profile.is_active or not profile.user.is_active or profile.user.user_type != "FORNECEDOR"
        ):
            raise serializers.ValidationError("Selecione um perfil ativo de fornecedor.")
        return profile

    def create(self, validated_data):
        from uuid import uuid4
        return super().create(dict(validated_data, source_key=f"hub:{uuid4()}"))


class TenderPublish(VersionWrite):
    deadline = serializers.DateTimeField()

    def validate_deadline(self, deadline):
        from django.utils import timezone
        if deadline <= timezone.now():
            raise serializers.ValidationError("Informe uma data futura.")
        return deadline


class TenderOfferWrite(OfferWrite):
    selected = serializers.HiddenField(default=False)


class TenderBidWrite(QuoteWrite):
    supplier_id = serializers.HiddenField(default=None)
    offers = TenderOfferWrite(many=True, allow_empty=False)
