from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("commercial", "0004_party_legacy_identity"),
    ]

    operations = [
        migrations.AddField(
            model_name="party",
            name="legacy_id",
            field=models.IntegerField(blank=True, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name="party",
            name="document",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=20,
                null=True,
            ),
        ),
    ]
