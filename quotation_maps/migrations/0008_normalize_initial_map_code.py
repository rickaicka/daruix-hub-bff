from django.db import migrations


def normalize_initial_map_codes(apps, schema_editor):
    Map = apps.get_model('quotation_maps', 'QuotationMap')
    Notification = apps.get_model('accounts', 'HubNotification')
    alias = schema_editor.connection.alias
    changes = []
    for quotation in Map.objects.using(alias).select_related('requisition__proposal').order_by('pk').iterator():
        if quotation.revision_number != 0:
            continue
        pc = quotation.requisition.proposal.code
        if len(pc) != 7 or not pc.startswith('PC') or not pc[2:].isdigit():
            raise ValueError(f'PC inválida para MC {quotation.pk}: {pc!r}')
        previous = f'MC{pc[2:]}-00'
        if quotation.code != previous:
            continue
        changes.append((quotation.pk, previous, f'MC{pc[2:]}'))
    targets = [target for _, _, target in changes]
    if len(set(targets)) != len(targets):
        raise ValueError('Códigos MC repetidos após normalização; migração interrompida.')
    ids = [pk for pk, _, _ in changes]
    if Map.objects.using(alias).exclude(pk__in=ids).filter(code__in=targets).exists():
        raise ValueError('Já existem MCs com códigos de destino; migração interrompida.')
    for pk, previous, target in changes:
        Map.objects.using(alias).filter(pk=pk).update(code=target)
        Notification.objects.using(alias).filter(
            event='quotation_map.ready', resource_type='quotation_map', resource_id=str(pk), message=previous,
        ).update(message=target)


class Migration(migrations.Migration):
    dependencies = [
        ('quotation_maps', '0007_standard_purchase_order_number'),
        ('material_requisitions', '0004_normalize_rm_number'),
    ]
    operations = [migrations.RunPython(normalize_initial_map_codes, migrations.RunPython.noop)]
