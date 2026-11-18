from django.core.management.base import BaseCommand
from django.db import transaction

from material_requisitions.models import MaterialRequisition, RMStatus
from quotation_maps.models import QuotationMap
from quotation_maps.services import create_for_approval, notify_ready


class Command(BaseCommand):
    help = "Cria mapas para RMs operacionais já aprovadas."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--notify", action="store_true")

    def handle(self, **options):
        candidates = MaterialRequisition.objects.filter(
            cancelled_at__isnull=True, approved_revision__status=RMStatus.APPROVED,
        )
        missing = candidates.exclude(pk__in=QuotationMap.objects.values("requisition_id"))
        if not options["apply"]:
            self.stdout.write(f"RMs aprovadas sem mapa: {missing.count()}")
            return
        for pk in missing.values_list("pk", flat=True).iterator():
            with transaction.atomic():
                rm = MaterialRequisition.objects.select_for_update().get(pk=pk)
                if rm.cancelled_at or not rm.approved_revision_id or rm.approved_revision.status != RMStatus.APPROVED:
                    continue
                quotation, created = create_for_approval(rm.approved_revision)
                if options["notify"] and created:
                    transaction.on_commit(lambda: notify_ready(quotation.pk, None), robust=True)
                if created:
                    self.stdout.write(quotation.code)
