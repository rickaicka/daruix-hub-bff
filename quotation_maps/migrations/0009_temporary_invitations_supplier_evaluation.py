from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('quotation_maps', '0008_normalize_initial_map_code')]
    operations = [
        migrations.AddField(model_name='supplier', name='payment_score', field=models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField(model_name='quotationmap', name='buyer', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='quotation_maps_bought', to='accounts.user')),
        migrations.AddField(model_name='purchaseorder', name='promised_delivery_at', field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name='purchaseorder', name='delivered_at', field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name='tenderbid', name='temp_username', field=models.CharField(blank=True, db_index=True, max_length=120)),
        migrations.AddField(model_name='tenderbid', name='temp_password_hash', field=models.CharField(blank=True, max_length=128)),
        migrations.AddField(model_name='tenderbid', name='invitation_token_hash', field=models.CharField(blank=True, db_index=True, max_length=64)),
        migrations.AddField(model_name='tenderbid', name='access_token_hash', field=models.CharField(blank=True, db_index=True, max_length=64)),
        migrations.AddField(model_name='tenderbid', name='expires_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='tenderbid', name='invited_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='tenderbid', name='emailed_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='tenderbid', name='email_error', field=models.TextField(blank=True)),
        migrations.AddField(model_name='tenderbid', name='revoked_at', field=models.DateTimeField(blank=True, null=True)),
    ]
