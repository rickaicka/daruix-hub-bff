import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Party",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("party_type", models.CharField(choices=[("INTERESTED", "Interessado"), ("CLIENT", "Cliente")], default="INTERESTED", max_length=12)),
                ("person_type", models.CharField(choices=[("INDIVIDUAL", "Pessoa física"), ("COMPANY", "Pessoa jurídica")], max_length=12)),
                ("legal_name", models.CharField(max_length=180)),
                ("trade_name", models.CharField(blank=True, max_length=150)),
                ("document", models.CharField(blank=True, max_length=20, null=True, unique=True)),
                ("state_registration", models.CharField(blank=True, max_length=30)),
                ("business_segment", models.CharField(blank=True, max_length=120)),
                ("website", models.URLField(blank=True)),
                ("notes", models.TextField(blank=True)),
                ("converted_at", models.DateTimeField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="parties_created", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="parties_updated", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "commercial_parties", "ordering": ("legal_name", "id")},
        ),
        migrations.CreateModel(
            name="Address",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(default="Principal", max_length=80)),
                ("postal_code", models.CharField(max_length=9)),
                ("street", models.CharField(max_length=180)),
                ("number", models.CharField(max_length=20)),
                ("complement", models.CharField(blank=True, max_length=120)),
                ("district", models.CharField(max_length=100)),
                ("city", models.CharField(max_length=100)),
                ("state", models.CharField(max_length=2)),
                ("is_primary", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("party", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="addresses", to="commercial.party")),
            ],
            options={"db_table": "commercial_addresses", "ordering": ("-is_primary", "label", "id")},
        ),
        migrations.CreateModel(
            name="Contact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150)),
                ("position", models.CharField(blank=True, max_length=120)),
                ("phone", models.CharField(blank=True, max_length=30)),
                ("mobile", models.CharField(blank=True, max_length=30)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("is_primary", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("party", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="contacts", to="commercial.party")),
            ],
            options={"db_table": "commercial_contacts", "ordering": ("-is_primary", "name", "id")},
        ),
        migrations.CreateModel(
            name="Proposal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(blank=True, max_length=20, unique=True)),
                ("entry_date", models.DateField()),
                ("division", models.CharField(max_length=40)),
                ("department", models.CharField(max_length=100)),
                ("work_name", models.CharField(max_length=180)),
                ("description", models.TextField(blank=True)),
                ("execution_days", models.PositiveIntegerField(blank=True, null=True)),
                ("expected_delivery_date", models.DateField(blank=True, null=True)),
                ("proposal_type", models.CharField(max_length=100)),
                ("status", models.CharField(choices=[("REQUESTED", "Solicitada"), ("BUDGETING", "Orçamento em elaboração"), ("SENT", "Enviada"), ("ACCEPTED", "Aceita"), ("REJECTED", "Recusada"), ("CANCELLED", "Cancelada")], default="REQUESTED", max_length=20)),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("issuer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="issued_proposals", to=settings.AUTH_USER_MODEL)),
                ("party", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="proposals", to="commercial.party")),
                ("requester_contact", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="proposals", to="commercial.contact")),
                ("technical_responsible", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="technical_proposals", to=settings.AUTH_USER_MODEL)),
                ("work_address", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="proposals", to="commercial.address")),
            ],
            options={"db_table": "commercial_proposals", "ordering": ("-entry_date", "-id")},
        ),
        migrations.AddIndex(model_name="party", index=models.Index(fields=["party_type", "is_active"], name="commercial__party_t_f8dfc0_idx")),
        migrations.AddIndex(model_name="proposal", index=models.Index(fields=["status", "entry_date"], name="commercial__status_8f2748_idx")),
        migrations.AddIndex(model_name="proposal", index=models.Index(fields=["party", "status"], name="commercial__party_i_f88db1_idx")),
    ]
