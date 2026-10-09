import hashlib

from django.db import migrations, models


RESOURCE_BY_MODEL = {
    "BusinessSegment": "business-segments",
    "CompanyType": "company-types",
}


def populate_legacy_keys(apps, schema_editor):
    for model_name, resource in RESOURCE_BY_MODEL.items():
        model = apps.get_model("commercial", model_name)
        for item in model.objects.filter(origin="LEGACY", legacy_id__isnull=False).iterator():
            item.legacy_key = hashlib.sha256(
                f"{resource}|id:{item.legacy_id}".encode("utf-8")
            ).hexdigest()
            item.save(update_fields=("legacy_key",))


class Migration(migrations.Migration):
    dependencies = [
        ("commercial", "0002_commercial_catalogs"),
        (
            "commercial",
            "0002_rename_commercial__party_t_f8dfc0_idx_commercial__party_t_771f62_idx_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="businesssegment",
            name="legacy_key",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="companytype",
            name="legacy_key",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.RunPython(populate_legacy_keys, migrations.RunPython.noop),
    ]
