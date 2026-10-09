from decimal import Decimal

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("budgeting", "0015_budget_sheet_item_snapshots"),
    ]

    operations = [
        migrations.AddField(
            model_name="budgetsheet",
            name="bdi_percentage",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("0"),
                help_text=(
                    "Percentual de BDI da revisão. Só é aplicado às composições "
                    "cuja linha esteja marcada com apply_bdi=True."
                ),
                max_digits=7,
                verbose_name="BDI (%)",
            ),
        ),
        migrations.AddField(
            model_name="budgetsheetstageitem",
            name="apply_bdi",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Quando verdadeiro em uma composição, o valor unitário da linha "
                    "é recalculado com o BDI da planilha. Não altera os filhos do snapshot."
                ),
                verbose_name="Aplicar BDI",
            ),
        ),
        migrations.AddConstraint(
            model_name="budgetsheet",
            constraint=models.CheckConstraint(
                condition=Q(bdi_percentage__gte=0),
                name="ck_budget_sheet_bdi_gte_0",
            ),
        ),
        migrations.AddConstraint(
            model_name="budgetsheetstageitem",
            constraint=models.CheckConstraint(
                condition=(Q(item_type="SERVICE_COMPOSITION") | Q(apply_bdi=False)),
                name="ck_budget_stage_item_bdi_only_composition",
            ),
        ),
    ]
