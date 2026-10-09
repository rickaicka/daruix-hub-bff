from decimal import Decimal

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("budgeting", "0014_budget_sheet_revisions"),
    ]

    operations = [
        migrations.AddField(
            model_name="budgetsheetstageitem",
            name="composition_version_number",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="Versão da composição utilizada",
            ),
        ),
        migrations.AddField(
            model_name="budgetsheetstageitem",
            name="material_unit_cost",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("0"),
                max_digits=18,
                verbose_name="Custo unitário de material",
            ),
        ),
        migrations.AddField(
            model_name="budgetsheetstageitem",
            name="labor_unit_cost",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("0"),
                max_digits=18,
                verbose_name="Custo unitário de mão de obra",
            ),
        ),
        migrations.AddField(
            model_name="budgetsheetstageitem",
            name="equipment_unit_cost",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("0"),
                max_digits=18,
                verbose_name="Custo unitário de equipamento",
            ),
        ),
        migrations.AddField(
            model_name="budgetsheetstageitem",
            name="unit_cost",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("0"),
                max_digits=18,
                verbose_name="Custo unitário total",
            ),
        ),
        migrations.AddField(
            model_name="budgetsheetstageitem",
            name="pricing_factor",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("0"),
                help_text=(
                    "Snapshot informativo de unit_price / unit_cost. "
                    "Não substitui a parametrização formal de BDI/DI."
                ),
                max_digits=18,
                verbose_name="Fator efetivo de venda",
            ),
        ),
        migrations.AddField(
            model_name="budgetsheetstageitem",
            name="composition_snapshot",
            field=models.JSONField(
                blank=True,
                default=dict,
                verbose_name="Snapshot da composição e de seus componentes",
            ),
        ),
        migrations.AddConstraint(
            model_name="budgetsheetstageitem",
            constraint=models.CheckConstraint(
                condition=(
                    Q(material_unit_cost__gte=0)
                    & Q(labor_unit_cost__gte=0)
                    & Q(equipment_unit_cost__gte=0)
                    & Q(unit_cost__gte=0)
                    & Q(pricing_factor__gte=0)
                ),
                name="ck_budget_stage_item_cost_snapshots_gte_0",
            ),
        ),
    ]
