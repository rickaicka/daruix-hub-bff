from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("budgeting", "0021_servicecompositionitem_precision")]
    operations = [
        migrations.CreateModel(
            name="ServiceCompositionGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(db_index=True, max_length=80)),
                ("name", models.CharField(max_length=255)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="children", to="budgeting.servicecompositiongroup")),
            ],
            options={"db_table": "budgeting_service_composition_group", "ordering": ("code", "name", "id")},
        ),
        migrations.AddConstraint(model_name="servicecompositiongroup", constraint=models.UniqueConstraint(fields=("parent", "code"), condition=Q(parent__isnull=False), name="uq_comp_group_child_code")),
        migrations.AddConstraint(model_name="servicecompositiongroup", constraint=models.UniqueConstraint(fields=("code",), condition=Q(parent__isnull=True), name="uq_comp_group_root_code")),
        migrations.AddField(model_name="servicecomposition", name="group", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="compositions", to="budgeting.servicecompositiongroup")),
    ]
