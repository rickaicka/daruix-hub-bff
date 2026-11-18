from django.db import migrations


def normalize_rm_codes(apps, schema_editor):
    Root = apps.get_model('material_requisitions', 'MaterialRequisition')
    alias = schema_editor.connection.alias
    changes = []
    for root in Root.objects.using(alias).select_related('proposal').order_by('pk').iterator():
        pc = root.proposal.code
        # Atualizamos apenas o formato operacional conhecido; nenhum identificador legado arbitrário.
        previous = f'RM-{pc}-{root.sequence:03d}'
        if root.number != previous:
            continue
        if len(pc) != 7 or not pc.startswith('PC') or not pc[2:].isdigit():
            raise ValueError(f'PC inválida para RM {root.pk}: {pc!r}')
        target = f'RM{pc[2:]}-{root.sequence:03d}'
        changes.append((root.pk, target))
    targets = [code for _, code in changes]
    if len(set(targets)) != len(targets):
        raise ValueError('Há colisões de códigos RM normalizados; migração interrompida.')
    ids = [pk for pk, _ in changes]
    if Root.objects.using(alias).exclude(pk__in=ids).filter(number__in=targets).exists():
        raise ValueError('Já existem RMs com um dos códigos de destino; migração interrompida.')
    for pk, target in changes:
        Root.objects.using(alias).filter(pk=pk).update(number=target)


class Migration(migrations.Migration):
    dependencies = [('material_requisitions', '0003_section_free_description')]
    operations = [migrations.RunPython(normalize_rm_codes, migrations.RunPython.noop)]
