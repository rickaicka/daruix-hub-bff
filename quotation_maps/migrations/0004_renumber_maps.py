from django.db import migrations


def renumber(apps, schema_editor):
    Map = apps.get_model("quotation_maps", "QuotationMap")
    maps = Map.objects.using(schema_editor.connection.alias).select_related("requisition__proposal")
    counters = {}
    for quotation in maps.order_by("created_at", "pk").iterator():
        proposal = quotation.requisition.proposal
        number = counters.get(proposal.pk, 0)
        quotation.revision_number = number
        quotation.code = f"MC{proposal.code.removeprefix('PC')}-{number:02d}"
        quotation.save(using=schema_editor.connection.alias, update_fields=["revision_number", "code"])
        counters[proposal.pk] = number + 1
        Notification = apps.get_model("accounts", "HubNotification")
        Notification.objects.using(schema_editor.connection.alias).filter(
            event="quotation_map.ready", resource_type="quotation_map", resource_id=str(quotation.pk),
        ).update(message=quotation.code)


class Migration(migrations.Migration):
    dependencies = [("quotation_maps", "0003_quotationmap_revision_number_and_more")]
    operations = [migrations.RunPython(renumber, migrations.RunPython.noop)]
