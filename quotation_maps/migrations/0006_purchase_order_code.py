from django.db import migrations, models

def populate_codes(apps, schema_editor):
    PurchaseOrder = apps.get_model('quotation_maps', 'PurchaseOrder')
    qs = PurchaseOrder.objects.select_related('quotation_map__requisition__proposal').order_by('created_at','pk')
    count = {}
    for order in qs.iterator(chunk_size=200):
        pc = order.quotation_map.requisition.proposal.code
        if not pc.startswith('PC') or not pc[2:].isdigit():
            raise ValueError(f'PC inválida ao migrar OC {order.pk}: {pc!r}')
        count[pc] = count.get(pc, 0) + 1
        order.code = f'HOC{pc[2:]}-{count[pc]:03d}'
        order.save(update_fields=['code'])

class Migration(migrations.Migration):
    dependencies = [('quotation_maps','0005_supplier_business_segment_supplier_delivery_terms_and_more')]
    operations = [
        migrations.AddField(model_name='purchaseorder', name='code', field=models.CharField(max_length=40, null=True, blank=True)),
        migrations.RunPython(populate_codes, migrations.RunPython.noop),
        migrations.AlterField(model_name='purchaseorder', name='code', field=models.CharField(max_length=40, unique=True)),
    ]
