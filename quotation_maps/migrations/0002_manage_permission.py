from django.db import migrations


def seed(apps, schema_editor):
    permission = apps.get_model("accounts", "Permission")
    permission.objects.using(schema_editor.connection.alias).get_or_create(
        code="quotation_map.manage",
        defaults={"module": "obras", "description": "Montar mapas de cotação e gerar ordens de compra"},
    )


class Migration(migrations.Migration):
    dependencies = [("quotation_maps", "0001_initial"), ("accounts", "0013_disable_rm_revise_and_clean_notifications")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
