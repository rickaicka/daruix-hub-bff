from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("budgeting", "0016_budget_sheet_bdi"),
    ]

    operations = [
        migrations.AddField(
            model_name="budgetsheet",
            name="bdi_configuration",
            field=models.JSONField(
                blank=True,
                default=dict,
                verbose_name="Memória de cálculo BDI",
            ),
        ),
        migrations.AddField(
            model_name="budgetsheet",
            name="di_configuration",
            field=models.JSONField(
                blank=True,
                default=dict,
                verbose_name="Memória de despesas indiretas",
            ),
        ),
        migrations.AlterField(
            model_name="budgetsheet",
            name="bdi_percentage",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("0"),
                help_text=(
                    "Resultado calculado/cache da memória BDI desta revisão. "
                    "Não deve ser editado diretamente pela API."
                ),
                max_digits=7,
                verbose_name="BDI calculado (%)",
            ),
        ),
    ]
