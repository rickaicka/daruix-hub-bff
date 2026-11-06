import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('material_requisitions', '0002_move_content_types')]
    operations = [migrations.AlterField(
        model_name='materialrequisitionsection', name='source_composition',
        field=models.ForeignKey(blank=True, null=True,
            on_delete=django.db.models.deletion.PROTECT, to='budgeting.budgetsheetstageitem'),
    )]
