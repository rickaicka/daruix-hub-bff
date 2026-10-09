from django.db import migrations, models
from django.db.models import Q


def normalize_budget_sheet_numbers(apps, schema_editor):
    BudgetSheet = apps.get_model("budgeting", "BudgetSheet")

    proposal_ids = (
        BudgetSheet.objects
        .filter(proposal_id__isnull=False, revision_root_id__isnull=True)
        .values_list("proposal_id", flat=True)
        .distinct()
    )

    for proposal_id in proposal_ids:
        roots = list(
            BudgetSheet.objects
            .filter(proposal_id=proposal_id, revision_root_id__isnull=True)
            .select_related("proposal")
            .order_by("id")
        )
        for sequence, root in enumerate(roots):
            proposal_code = str(root.proposal.code or "").strip().upper()
            if proposal_code.startswith("PC"):
                proposal_code = proposal_code[2:]
            number = f"{proposal_code}-{sequence:02d}"

            BudgetSheet.objects.filter(pk=root.pk).update(
                proposal_sequence=sequence,
                number=number,
            )
            BudgetSheet.objects.filter(revision_root_id=root.pk).update(
                proposal_sequence=sequence,
                number=number,
            )


def noop_reverse(apps, schema_editor):
    # A volta para o modelo antigo (uma raiz por proposta) perderia informação
    # quando já existirem duas planilhas independentes no mesmo PC.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("budgeting", "0019_budget_item_unit_discount"),
    ]

    operations = [
        migrations.AddField(
            model_name="budgetsheet",
            name="proposal_sequence",
            field=models.PositiveIntegerField(
                default=0,
                help_text=(
                    "Identifica planilhas independentes vinculadas à mesma proposta/PC. "
                    "Cada sequência possui seu próprio histórico de revisões."
                ),
                verbose_name="Sequência da planilha no PC",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="budgetsheet",
            name="uq_budget_sheet_proposal_revision",
        ),
        migrations.AlterField(
            model_name="budgetsheet",
            name="number",
            field=models.CharField(max_length=50, verbose_name="Número do orçamento"),
        ),
        migrations.RunPython(normalize_budget_sheet_numbers, noop_reverse),
        migrations.AddConstraint(
            model_name="budgetsheet",
            constraint=models.UniqueConstraint(
                condition=Q(proposal__isnull=False),
                fields=("proposal", "proposal_sequence", "revision"),
                name="uq_budget_sheet_proposal_sequence_revision",
            ),
        ),
        migrations.AddConstraint(
            model_name="budgetsheet",
            constraint=models.UniqueConstraint(
                fields=("number", "revision"),
                name="uq_budget_sheet_number_revision",
            ),
        ),
    ]
