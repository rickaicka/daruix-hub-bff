from django.db import migrations


def create_rm_approve_permission(apps, schema_editor):
    Permission = apps.get_model('accounts', 'Permission')
    Permission.objects.get_or_create(
        code='material_requisition.approve',
        defaults={'module': 'material_requisitions', 'description': 'Aprovar/reprovar RM como responsável técnico da obra', 'is_active': True},
    )


class Migration(migrations.Migration):
    dependencies = [('accounts', '0011_hubnotification_generic_metadata')]
    operations = [migrations.RunPython(create_rm_approve_permission, migrations.RunPython.noop)]
