from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("commercial", "0007_proposal_relational_structure"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="proposalrequestedservice",
            name="commercial_unique_project_per_proposal",
        ),
    ]
