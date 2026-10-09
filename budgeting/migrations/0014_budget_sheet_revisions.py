import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("budgeting", "0013_add_budget_sheet_stage_items"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="budgetsheet",
            name="revision_root",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="revisions",
                to="budgeting.budgetsheet",
                verbose_name="Planilha original",
            ),
        ),
        migrations.AddField(
            model_name="budgetsheet",
            name="previous_revision",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="next_revision",
                to="budgeting.budgetsheet",
                verbose_name="Revisão anterior",
            ),
        ),
        migrations.AddField(
            model_name="budgetsheet",
            name="revision_reason",
            field=models.TextField(
                blank=True,
                default="",
                verbose_name="Motivo da revisão",
            ),
        ),
        migrations.AddField(
            model_name="budgetsheet",
            name="finalized_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="budget_sheets_finalized",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="budgetsheet",
            name="finalized_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name="budgetsheet",
            index=models.Index(
                fields=["revision_root", "revision"],
                name="budget_revision_group_idx",
            ),
        ),
    ]
