from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("commercial", "0005_party_legacy_id_document_non_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="party",
            name="last_service",
            field=models.CharField(blank=True, max_length=180),
        ),
        migrations.AddField(
            model_name="party",
            name="referred_by",
            field=models.CharField(blank=True, max_length=180),
        ),
    ]
