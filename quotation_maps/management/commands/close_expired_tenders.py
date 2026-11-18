from django.core.management.base import BaseCommand
from quotation_maps.invitations import close_expired_tenders


class Command(BaseCommand):
    help = "Encerra e consolida leilões cujo prazo terminou (idempotente)."

    def handle(self, *args, **options):
        self.stdout.write(f"Leilões encerrados: {close_expired_tenders()}")
