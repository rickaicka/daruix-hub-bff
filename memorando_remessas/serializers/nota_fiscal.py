from rest_framework import serializers
from memorando_remessas.models.nota_fiscal import ShipmentMemoInvoice

class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShipmentMemoInvoice
        fields = ['id','number','series','issuer_name','trade_name','issuer_document','total_value','access_key','description','source']
        read_only_fields = ['id']

    def validate_number(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Número da NF obrigatório.')
        return value

class InvoiceBatchSerializer(serializers.Serializer):
    invoices = InvoiceSerializer(many=True, allow_empty=True)
