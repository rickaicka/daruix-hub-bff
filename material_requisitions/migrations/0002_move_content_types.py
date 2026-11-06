from django.db import migrations

MODELS = ('materialrequisition', 'materialrequisitionrevision', 'materialrequisitionsection',
          'materialrequisitionitem', 'materialrequisitionevent', 'legacymaterialrequest',
          'legacymaterialrequestitem', 'legacymaterialrequestissue')


def move(apps, schema_editor, source, target):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    db = schema_editor.connection.alias
    # Preserva PK de ContentType, permissões, grupos, usuários e referências genéricas.
    # Valida todos antes da primeira alteração para evitar movimento parcial.
    for model in MODELS:
        if (ContentType.objects.using(db).filter(app_label=source, model=model).exists()
                and ContentType.objects.using(db).filter(app_label=target, model=model).exists()):
            raise RuntimeError(f'ContentType duplicado para {model}; reconcilie antes de migrar.')
    ContentType.objects.using(db).filter(app_label=source, model__in=MODELS).update(app_label=target)


def forwards(apps, schema_editor):
    move(apps, schema_editor, 'budgeting', 'material_requisitions')


def backwards(apps, schema_editor):
    move(apps, schema_editor, 'material_requisitions', 'budgeting')


class Migration(migrations.Migration):
    dependencies = [
        ('material_requisitions', '0001_adopt_existing_rm_tables'),
        ('budgeting', '0025_move_rm_to_material_requisitions'),
    ]
    operations = [migrations.RunPython(forwards, backwards)]
