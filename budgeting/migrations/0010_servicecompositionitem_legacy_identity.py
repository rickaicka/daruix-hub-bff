from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("budgeting", "0009_supply_created_by_supply_updated_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicecompositionitem",
            name="legacy_table",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="servicecompositionitem",
            name="legacy_id",
            field=models.BigIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="servicecompositionitem",
            constraint=models.UniqueConstraint(
                fields=("legacy_table", "legacy_id"),
                condition=Q(legacy_id__isnull=False),
                name="uq_composition_item_legacy_source",
            ),
        ),
    ]
