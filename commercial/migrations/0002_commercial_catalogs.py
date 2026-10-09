import django.db.models.deletion
from django.db import migrations, models


def preserve_business_segments(apps, schema_editor):
    Party = apps.get_model("commercial", "Party")
    BusinessSegment = apps.get_model("commercial", "BusinessSegment")
    for party in Party.objects.exclude(legacy_business_segment_name="").iterator():
        name = party.legacy_business_segment_name.strip()
        if not name:
            continue
        segment, _ = BusinessSegment.objects.get_or_create(
            name__iexact=name,
            defaults={"name": name, "origin": "HUB", "is_active": True},
        )
        party.business_segment_id = segment.id
        party.save(update_fields=("business_segment",))


class Migration(migrations.Migration):
    dependencies = [("commercial", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="BusinessSegment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("origin", models.CharField(choices=[("LEGACY", "Legado"), ("HUB", "Hub")], default="LEGACY", max_length=10)),
                ("legacy_id", models.IntegerField(blank=True, null=True, unique=True)),
                ("name", models.CharField(max_length=150)),
                ("is_active", models.BooleanField(default=True)),
                ("legacy_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Ramo empresarial",
                "verbose_name_plural": "Ramos empresariais",
                "db_table": "commercial_business_segments",
                "ordering": ("name", "id"),
            },
        ),
        migrations.CreateModel(
            name="CompanyType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("origin", models.CharField(choices=[("LEGACY", "Legado"), ("HUB", "Hub")], default="LEGACY", max_length=10)),
                ("legacy_id", models.IntegerField(blank=True, null=True, unique=True)),
                ("name", models.CharField(max_length=150)),
                ("is_active", models.BooleanField(default=True)),
                ("legacy_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Tipo de empresa",
                "verbose_name_plural": "Tipos de empresa",
                "db_table": "commercial_company_types",
                "ordering": ("name", "id"),
            },
        ),
        migrations.RenameField(
            model_name="party",
            old_name="business_segment",
            new_name="legacy_business_segment_name",
        ),
        migrations.AddField(
            model_name="party",
            name="business_segment",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="parties", to="commercial.businesssegment"),
        ),
        migrations.AddField(
            model_name="party",
            name="company_type",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="parties", to="commercial.companytype"),
        ),
        migrations.RunPython(preserve_business_segments, migrations.RunPython.noop),
        migrations.RemoveField(model_name="party", name="legacy_business_segment_name"),
    ]
