from django.core.management.base import BaseCommand, CommandError
from material_requisitions.services.import_legacy_material_requests import prepare, persist


class Command(BaseCommand):
    help = 'Analisa RMs legadas; com --apply grava espelho não operacional.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Grava o lote após leitura completa.')
        parser.add_argument('--page-size', type=int, default=500)

    def handle(self, *args, **options):
        try:
            prepared = prepare(page_size=options['page_size'])
            counts = persist(prepared) if options['apply'] else prepared.counts
        except Exception as error:
            raise CommandError(f'Importação de RM não concluída: {error}') from error
        self.stdout.write('Modo: ' + ('GRAVAÇÃO' if options['apply'] else 'SIMULAÇÃO'))
        for key in sorted(counts):
            self.stdout.write(f'{key}: {counts[key]}')
        self.stdout.write('Registros ausentes na origem não são removidos.')
