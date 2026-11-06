from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('memorando_remessas', '0012_alter_shipmentmemoinvoice_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shipmentmemoinvoice',
            name='access_key',
            field=models.CharField(max_length=50, blank=True, default=''),
        ),
    ]
