from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("commercial", "0003_catalog_legacy_key")]

    operations = [
        migrations.AddField(
            model_name="party",
            name="origin",
            field=models.CharField(
                choices=[("LEGACY", "Legado"), ("HUB", "Hub")],
                default="HUB",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="party",
            name="legacy_key",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="party",
            name="legacy_payload",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
