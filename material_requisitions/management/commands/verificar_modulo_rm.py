from django.core.management.base import BaseCommand
from material_requisitions import models


class Command(BaseCommand):
    help = 'Confere os modelos e as contagens da RM após a separação, sem alterar dados.'

    def handle(self, *args, **options):
        for name in ('MaterialRequisition', 'MaterialRequisitionRevision', 'MaterialRequisitionSection',
                     'MaterialRequisitionItem', 'MaterialRequisitionEvent', 'LegacyMaterialRequest',
                     'LegacyMaterialRequestItem', 'LegacyMaterialRequestIssue'):
            model = getattr(models, name)
            self.stdout.write(f'{model._meta.label}: {model.objects.count()}')
