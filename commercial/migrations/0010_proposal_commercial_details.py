from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('commercial', '0009_add_proposal_issuer_name')]
    operations = [migrations.AddField(
        model_name='proposal', name='commercial_details',
        field=models.JSONField(blank=True, default=dict),
    )]
