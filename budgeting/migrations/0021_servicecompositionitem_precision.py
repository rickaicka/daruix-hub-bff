from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("budgeting", "0020_budget_sheet_multiple_per_proposal"),
    ]

    operations = [
        migrations.AlterField(
            model_name="servicecompositionitem",
            name="material_unit_price",
            field=models.DecimalField(
                decimal_places=8,
                default=0,
                max_digits=22,
            ),
        ),
        migrations.AlterField(
            model_name="servicecompositionitem",
            name="labor_unit_price",
            field=models.DecimalField(
                decimal_places=8,
                default=0,
                max_digits=22,
            ),
        ),
        migrations.AlterField(
            model_name="servicecompositionitem",
            name="equipment_unit_price",
            field=models.DecimalField(
                decimal_places=8,
                default=0,
                max_digits=22,
            ),
        ),
    ]