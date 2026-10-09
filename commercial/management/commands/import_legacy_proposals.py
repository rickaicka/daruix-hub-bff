from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from commercial.services.legacy_proposals import LegacyProposalImporter
from integrations.legacy_bridge import LegacyBridgeClient, LegacyBridgeHttpError


RESOURCES = (
    "proposal-types",
    "departments",
    "projects",
    "proposals",
    "proposal-requested-services",
    "proposal-contacts",
    "proposal-payment-installments",
    "proposal-payment-plans",
)


class Command(BaseCommand):
    help = "Importa propostas e seus relacionamentos do Access via Legacy Bridge."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--page-size", type=int, default=500)

    def handle(self, *args, **options):
        page_size = options["page_size"]
        if page_size < 1 or page_size > 1000:
            raise CommandError("--page-size deve estar entre 1 e 1000.")

        client = LegacyBridgeClient()
        data = {}

        try:
            for resource in RESOURCES:
                self.stdout.write(f"Lendo {resource}...")
                data[resource] = list(
                    client.iter_commercial_resource(
                        resource,
                        page_size=page_size,
                        on_page_response=self._page_response,
                    )
                )
        except (LegacyBridgeHttpError, ValueError) as error:
            raise CommandError(str(error)) from error

        with transaction.atomic():
            self.stdout.write(
                f"Processando {len(data['proposals'])} propostas..."
            )
            stats = LegacyProposalImporter(
                progress_callback=self._proposal_progress,
                progress_every=250,
            ).import_all(
                proposal_types=data["proposal-types"],
                departments=data["departments"],
                projects=data["projects"],
                proposals=data["proposals"],
                requested_services=data["proposal-requested-services"],
                proposal_contacts=data["proposal-contacts"],
                payment_installments=data["proposal-payment-installments"],
                payment_plans=data["proposal-payment-plans"],
            )

            if options["dry_run"]:
                transaction.set_rollback(True)

        for key in sorted(stats):
            self.stdout.write(f"{key}: {stats[key]}")

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING("Dry-run: nenhuma alteração persistida.")
            )
        else:
            self.stdout.write(self.style.SUCCESS("Importação de propostas concluída."))

    def _page_response(
        self,
        resource: str,
        offset: int,
        item_count: int,
        has_more: bool,
    ) -> None:
        self.stdout.write(
            f"  {resource}: offset={offset}, itens={item_count}, "
            f"continua={'sim' if has_more else 'não'}"
        )

    def _proposal_progress(self, processed: int, total: int) -> None:
        percentage = (processed / total * 100) if total else 100
        self.stdout.write(
            f"  Propostas: {processed}/{total} ({percentage:.1f}%)"
        )
