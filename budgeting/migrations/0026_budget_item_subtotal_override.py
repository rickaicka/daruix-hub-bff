from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("budgeting", "0025_move_rm_to_material_requisitions"),
    ]

    operations = [
        migrations.AddField(
            model_name="budgetsheetstageitem",
            name="subtotal_override",
            field=models.DecimalField(
                max_digits=18,
                decimal_places=2,
                null=True,
                blank=True,
                validators=[MinValueValidator(Decimal("0"))],
                verbose_name="Total fixo da linha",
            ),
        ),
    ]
