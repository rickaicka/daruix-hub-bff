from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('accounts', '0010_hubnotification')]
    operations = [
        migrations.AddField(model_name='hubnotification', name='module', field=models.CharField(max_length=64, blank=True, db_index=True)),
        migrations.AddField(model_name='hubnotification', name='event', field=models.CharField(max_length=100, blank=True, db_index=True)),
        migrations.AddField(model_name='hubnotification', name='resource_type', field=models.CharField(max_length=100, blank=True)),
        migrations.AddField(model_name='hubnotification', name='resource_id', field=models.CharField(max_length=100, blank=True)),
        migrations.AddField(model_name='hubnotification', name='payload', field=models.JSONField(default=dict, blank=True)),
    ]
