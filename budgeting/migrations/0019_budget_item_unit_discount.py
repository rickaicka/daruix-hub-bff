from decimal import Decimal
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('budgeting', '0018_supply_bdi')]
    operations = [migrations.AddField(
        model_name='budgetsheetstageitem', name='unit_discount',
        field=models.DecimalField(max_digits=18, decimal_places=2,
                                  default=Decimal('0'), verbose_name='Desconto unitário (R$)'),
    )]
