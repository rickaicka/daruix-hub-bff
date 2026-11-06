from django.db import migrations
import re


LEGACY_PERMISSION = 'material_requisition.revise'


def forward(apps, schema_editor):
    Permission = apps.get_model('accounts', 'Permission')
    Notification = apps.get_model('accounts', 'HubNotification')
    Permission.objects.filter(code=LEGACY_PERMISSION).update(is_active=False)
    qs = Notification.objects.filter(module='obras', resource_type='material_requisition')
    # Mantém os IDs/chaves de notificação e revision_id da API legada.
    for notification in qs.iterator(chunk_size=500):
        original = notification.message or ''
        cleaned = re.sub(r'\s*[·•-]\s*R\d{2,}\s*$', '', original).strip()
        if cleaned != original:
            Notification.objects.filter(pk=notification.pk).update(message=cleaned)


def backward(apps, schema_editor):
    # Não reativa permissão automaticamente nem reconstrói mensagens antigas.
    # Reverter o código não deve reabrir o fluxo inseguro de revisão.
    pass


class Migration(migrations.Migration):
    dependencies = [('accounts', '0012_rm_approve_permission')]
    operations = [migrations.RunPython(forward, backward)]
