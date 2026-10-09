import hashlib

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _catalog_key(resource, value):
    normalized = " ".join(str(value or "").strip().upper().split())
    return hashlib.sha256(f"hub-migration|{resource}|{normalized}".encode("utf-8")).hexdigest()


def migrate_proposal_catalogs(apps, schema_editor):
    Proposal = apps.get_model("commercial", "Proposal")
    Division = apps.get_model("commercial", "Division")
    Department = apps.get_model("commercial", "Department")
    ProposalType = apps.get_model("commercial", "ProposalType")

    for proposal in Proposal.objects.all().iterator():
        division_name = str(proposal.legacy_division_name or "").strip()
        department_name = str(proposal.legacy_department_name or "").strip()
        proposal_type_name = str(proposal.legacy_proposal_type_name or "").strip()

        division = None
        if division_name:
            division, _ = Division.objects.get_or_create(
                code=division_name[:20].upper(),
                defaults={
                    "name": division_name[:150],
                    "origin": "HUB",
                    "legacy_key": _catalog_key("division", division_name),
                },
            )

        department = None
        if department_name:
            department_key = _catalog_key(
                "department",
                f"{division_name}|{department_name}",
            )
            department = Department.objects.filter(legacy_key=department_key).first()
            if department is None:
                department = Department.objects.create(
                    name=department_name[:150],
                    division=division,
                    origin="HUB",
                    legacy_key=department_key,
                )

        proposal_type = None
        if proposal_type_name:
            type_key = _catalog_key("proposal-type", proposal_type_name)
            proposal_type = ProposalType.objects.filter(legacy_key=type_key).first()
            if proposal_type is None:
                proposal_type = ProposalType.objects.create(
                    name=proposal_type_name[:150],
                    origin="HUB",
                    legacy_key=type_key,
                )

        proposal.division_ref = division
        proposal.department_ref = department
        proposal.proposal_type_ref = proposal_type
        proposal.save(
            update_fields=(
                "division_ref",
                "department_ref",
                "proposal_type_ref",
            )
        )


class Migration(migrations.Migration):
    dependencies = [
        ("commercial", "0006_party_last_service_party_referred_by"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Division",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("origin", models.CharField(choices=[("LEGACY", "Legado"), ("HUB", "Hub")], default="LEGACY", max_length=10)),
                ("legacy_id", models.IntegerField(blank=True, null=True, unique=True)),
                ("legacy_key", models.CharField(blank=True, max_length=64, null=True, unique=True)),
                ("name", models.CharField(max_length=150)),
                ("is_active", models.BooleanField(default=True)),
                ("legacy_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(max_length=20, unique=True)),
            ],
            options={
                "verbose_name": "Divisão",
                "verbose_name_plural": "Divisões",
                "db_table": "commercial_divisions",
                "ordering": ("name", "id"),
            },
        ),
        migrations.CreateModel(
            name="ProposalType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("origin", models.CharField(choices=[("LEGACY", "Legado"), ("HUB", "Hub")], default="LEGACY", max_length=10)),
                ("legacy_id", models.IntegerField(blank=True, null=True, unique=True)),
                ("legacy_key", models.CharField(blank=True, max_length=64, null=True, unique=True)),
                ("name", models.CharField(max_length=150)),
                ("is_active", models.BooleanField(default=True)),
                ("legacy_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Tipo de proposta",
                "verbose_name_plural": "Tipos de proposta",
                "db_table": "commercial_proposal_types",
                "ordering": ("name", "id"),
            },
        ),
        migrations.CreateModel(
            name="Department",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("origin", models.CharField(choices=[("LEGACY", "Legado"), ("HUB", "Hub")], default="LEGACY", max_length=10)),
                ("legacy_id", models.IntegerField(blank=True, null=True, unique=True)),
                ("legacy_key", models.CharField(blank=True, max_length=64, null=True, unique=True)),
                ("name", models.CharField(max_length=150)),
                ("is_active", models.BooleanField(default=True)),
                ("legacy_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("abbreviation", models.CharField(blank=True, max_length=20)),
                ("division", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="departments", to="commercial.division")),
            ],
            options={
                "verbose_name": "Departamento",
                "verbose_name_plural": "Departamentos",
                "db_table": "commercial_departments",
                "ordering": ("name", "id"),
            },
        ),
        migrations.CreateModel(
            name="Project",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("origin", models.CharField(choices=[("LEGACY", "Legado"), ("HUB", "Hub")], default="LEGACY", max_length=10)),
                ("legacy_id", models.IntegerField(blank=True, null=True, unique=True)),
                ("legacy_key", models.CharField(blank=True, max_length=64, null=True, unique=True)),
                ("name", models.CharField(max_length=150)),
                ("is_active", models.BooleanField(default=True)),
                ("legacy_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("department", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="projects", to="commercial.department")),
            ],
            options={
                "verbose_name": "Projeto/serviço",
                "verbose_name_plural": "Projetos/serviços",
                "db_table": "commercial_projects",
                "ordering": ("name", "id"),
            },
        ),
        migrations.AddField(
            model_name="proposal",
            name="origin",
            field=models.CharField(choices=[("LEGACY", "Legado"), ("HUB", "Hub")], default="HUB", max_length=10),
        ),
        migrations.AddField(model_name="proposal", name="legacy_id", field=models.IntegerField(blank=True, null=True, unique=True)),
        migrations.AddField(model_name="proposal", name="legacy_key", field=models.CharField(blank=True, max_length=64, null=True, unique=True)),
        migrations.AddField(model_name="proposal", name="legacy_payload", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="proposal", name="contract_value", field=models.DecimalField(decimal_places=2, default=0, max_digits=14)),
        migrations.AddField(model_name="proposal", name="additional_value", field=models.DecimalField(decimal_places=2, default=0, max_digits=14)),
        migrations.RenameField(model_name="proposal", old_name="division", new_name="legacy_division_name"),
        migrations.RenameField(model_name="proposal", old_name="department", new_name="legacy_department_name"),
        migrations.RenameField(model_name="proposal", old_name="proposal_type", new_name="legacy_proposal_type_name"),
        migrations.AddField(
            model_name="proposal",
            name="division_ref",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="proposals", to="commercial.division"),
        ),
        migrations.AddField(
            model_name="proposal",
            name="department_ref",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="proposals", to="commercial.department"),
        ),
        migrations.AddField(
            model_name="proposal",
            name="proposal_type_ref",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="proposals", to="commercial.proposaltype"),
        ),
        migrations.RunPython(migrate_proposal_catalogs, migrations.RunPython.noop),
        migrations.RemoveField(model_name="proposal", name="legacy_division_name"),
        migrations.RemoveField(model_name="proposal", name="legacy_department_name"),
        migrations.RemoveField(model_name="proposal", name="legacy_proposal_type_name"),
        migrations.RenameField(model_name="proposal", old_name="division_ref", new_name="division"),
        migrations.RenameField(model_name="proposal", old_name="department_ref", new_name="department"),
        migrations.RenameField(model_name="proposal", old_name="proposal_type_ref", new_name="proposal_type"),
        migrations.AlterField(
            model_name="proposal",
            name="work_address",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="proposals", to="commercial.address"),
        ),
        migrations.AlterField(
            model_name="proposal",
            name="requester_contact",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="proposals", to="commercial.contact"),
        ),
        migrations.AlterField(
            model_name="proposal",
            name="technical_responsible",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="technical_proposals", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name="proposal",
            name="issuer",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="issued_proposals", to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name="ProposalRequestedService",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("area", models.DecimalField(blank=True, decimal_places=4, max_digits=14, null=True)),
                ("proposed_value", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("contracted_value", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("position", models.CharField(blank=True, max_length=80)),
                ("completion_date", models.DateField(blank=True, null=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("origin", models.CharField(choices=[("LEGACY", "Legado"), ("HUB", "Hub")], default="HUB", max_length=10)),
                ("legacy_id", models.IntegerField(blank=True, null=True, unique=True)),
                ("legacy_key", models.CharField(blank=True, max_length=64, null=True, unique=True)),
                ("legacy_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="proposal_items", to="commercial.project")),
                ("proposal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="requested_services", to="commercial.proposal")),
            ],
            options={"db_table": "commercial_proposal_requested_services", "ordering": ("sort_order", "id")},
        ),
        migrations.CreateModel(
            name="ProposalContact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("context", models.CharField(choices=[("CLIENT", "Cliente"), ("WORK", "Obra")], default="CLIENT", max_length=10)),
                ("is_primary", models.BooleanField(default=False)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("origin", models.CharField(choices=[("LEGACY", "Legado"), ("HUB", "Hub")], default="HUB", max_length=10)),
                ("legacy_key", models.CharField(blank=True, max_length=64, null=True, unique=True)),
                ("legacy_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("contact", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="proposal_links", to="commercial.contact")),
                ("proposal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="proposal_contacts", to="commercial.proposal")),
            ],
            options={"db_table": "commercial_proposal_contacts", "ordering": ("context", "sort_order", "id")},
        ),
        migrations.CreateModel(
            name="ProposalInstallment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=30)),
                ("sequence", models.PositiveIntegerField(blank=True, null=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("due_date", models.DateField(blank=True, null=True)),
                ("paid_at", models.DateField(blank=True, null=True)),
                ("status", models.CharField(choices=[("OPEN", "Em aberto"), ("PAID", "Quitada"), ("CANCELLED", "Cancelada"), ("UNKNOWN", "Não informada")], default="UNKNOWN", max_length=12)),
                ("source", models.CharField(choices=[("HUB", "Hub"), ("LEGACY_INSTALLMENTS", "Pagamento parcelado"), ("LEGACY_PAYMENT_PLAN", "Plano de pagamento")], default="HUB", max_length=24)),
                ("legacy_id", models.IntegerField(blank=True, null=True)),
                ("legacy_key", models.CharField(blank=True, max_length=64, null=True, unique=True)),
                ("legacy_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("proposal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="installments", to="commercial.proposal")),
            ],
            options={"db_table": "commercial_proposal_installments", "ordering": ("sequence", "due_date", "id")},
        ),
        migrations.AddConstraint(
            model_name="proposalrequestedservice",
            constraint=models.UniqueConstraint(fields=("proposal", "project"), name="commercial_unique_project_per_proposal"),
        ),
        migrations.AddConstraint(
            model_name="proposalcontact",
            constraint=models.UniqueConstraint(fields=("proposal", "contact", "context"), name="commercial_unique_contact_per_context"),
        ),
        migrations.AddConstraint(
            model_name="proposalinstallment",
            constraint=models.UniqueConstraint(condition=models.Q(sequence__isnull=False), fields=("proposal", "sequence"), name="commercial_unique_installment_sequence"),
        ),
    ]
