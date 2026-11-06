from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('accounts', '0009_hubmenuitem_descricao'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name='HubNotification', fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('key', models.CharField(max_length=160)), ('kind', models.CharField(max_length=48)),
        ('title', models.CharField(max_length=180)), ('message', models.TextField(blank=True)),
        ('route', models.CharField(max_length=500, blank=True)),
        ('read_at', models.DateTimeField(blank=True, null=True)),
        ('resolved_at', models.DateTimeField(blank=True, null=True)),
        ('created_at', models.DateTimeField(auto_now_add=True)),
        ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
        ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='hub_notifications', to=settings.AUTH_USER_MODEL)),
    ], options={'ordering': ('-created_at', '-id')}),
    migrations.AddConstraint(model_name='hubnotification', constraint=models.UniqueConstraint(fields=('recipient', 'key'), name='uniq_hub_notice_recipient_key'))]
