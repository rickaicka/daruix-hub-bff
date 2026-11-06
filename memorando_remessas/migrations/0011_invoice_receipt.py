from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('memorando_remessas', '0010_alter_shipmentmemooption_option_type')]
    operations = [
        migrations.AddField(model_name='shipmentmemo', name='received_by_name', field=models.CharField(blank=True, default='', max_length=180)),
        migrations.AddField(model_name='shipmentmemo', name='received_at', field=models.DateField(blank=True, null=True)),
        migrations.CreateModel(name='ShipmentMemoInvoice', fields=[
            ('id', models.BigAutoField(primary_key=True, serialize=False)),
            ('number', models.CharField(max_length=30)),
            ('series', models.CharField(blank=True, default='', max_length=12)),
            ('issuer_name', models.CharField(blank=True, default='', max_length=255)),
            ('trade_name', models.CharField(blank=True, default='', max_length=255)),
            ('issuer_document', models.CharField(blank=True, default='', max_length=20)),
            ('total_value', models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True)),
            ('access_key', models.CharField(blank=True, default='', max_length=44)),
            ('description', models.CharField(blank=True, default='', max_length=255)),
            ('source', models.CharField(default='MANUAL', max_length=16)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('memo', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invoices', to='memorando_remessas.shipmentmemo')),
        ],options={'ordering':['id']})]
