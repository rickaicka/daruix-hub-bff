"""Numeração por PC, iniciada em 001, independente dos convites."""
from collections import defaultdict
from django.db import migrations


def renumber_maps(apps, schema_editor):
    alias = schema_editor.connection.alias
    Map = apps.get_model("quotation_maps", "QuotationMap")
    Notification = apps.get_model("accounts", "HubNotification")

    # Um mapa continua sendo identificado pelo PK; não modificamos convites,
    # ofertas, ligações à RM ou ordens de compra.
    maps = list(
        Map.objects.using(alias)
        .select_related("requisition__proposal")
        .order_by("created_at", "pk")
    )
    counters = defaultdict(int)
    changes = []
    for quotation in maps:
        proposal = quotation.requisition.proposal
        pc = proposal.code
        if not pc.startswith("PC") or not pc[2:].isdigit():
            raise ValueError(f"PC inválida para mapa {quotation.pk}: {pc!r}")
        counters[proposal.pk] += 1
        sequence = counters[proposal.pk]
        new_code = f"MC{pc[2:]}-{sequence:03d}"
        changes.append((quotation.pk, quotation.code, new_code, sequence))

    targets = [entry[2] for entry in changes]
    if len(targets) != len(set(targets)):
        raise ValueError("Códigos de mapas duplicados na renumeração; operação cancelada.")

    # Evita colisão da restrição UNIQUE se um código futuro já estiver em uso.
    # A migração é transacional no PostgreSQL; qualquer falha reverte tudo.
    for pk, _, _, _ in changes:
        Map.objects.using(alias).filter(pk=pk).update(code=f"__mc_sequence_migration_{pk}__")

    for pk, old_code, new_code, sequence in changes:
        Map.objects.using(alias).filter(pk=pk).update(
            code=new_code, revision_number=sequence,
        )
        Notification.objects.using(alias).filter(
            event="quotation_map.ready",
            resource_type="quotation_map",
            resource_id=str(pk),
            message=old_code,
        ).update(message=new_code)


class Migration(migrations.Migration):
    dependencies = [("quotation_maps", "0010_reverse_auction_participate")]
    operations = [migrations.RunPython(renumber_maps, migrations.RunPython.noop)]
