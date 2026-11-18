import os
import json
from django.conf import settings
from django.db import migrations


def renumber_hub_codes(apps, schema_editor):
    """Renomeia códigos provisórios; NÃO afirma exclusividade no legado.

    Antes de aplicar em produção, concilie números legados para cada PC:
    migrar para 001 aqui pode conflitar com uma OC preexistente fora do Hub.
    """
    PurchaseOrder = apps.get_model('quotation_maps', 'PurchaseOrder')
    qs = PurchaseOrder.objects.select_related('quotation_map__requisition__proposal').order_by('created_at','pk')
    mapping = getattr(settings, 'OC_LEGACY_LAST_BY_PC', None)
    if mapping is None:
        mapping = os.environ.get('OC_LEGACY_LAST_BY_PC', '{}')
    if isinstance(mapping, str):
        mapping = json.loads(mapping)
    sequences = {}
    for order in qs.iterator(chunk_size=200):
        pc = order.quotation_map.requisition.proposal.code
        if len(pc)!=7 or not pc.startswith('PC') or not pc[2:].isdigit():
            raise ValueError(f'PC inválida para OC {order.pk}: {pc!r}')
        if pc not in mapping:
            raise ValueError(f'Migration interrompida: concilie a última OC legada de {pc} (0 se nenhuma).')
        sequences[pc] = sequences.get(pc, int(mapping[pc])) + 1
        if sequences[pc]>999: raise ValueError(f'Mais de 999 OCs para {pc}')
        code = f'OC{pc[2:]}{sequences[pc]:03d}'
        order.code = code
        order.save(update_fields=['code'])


class Migration(migrations.Migration):
    dependencies = [('quotation_maps','0006_purchase_order_code')]
    operations = [migrations.RunPython(renumber_hub_codes, migrations.RunPython.noop)]
