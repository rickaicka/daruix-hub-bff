from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.utils import timezone

from budgeting.choices import (
    ImportResource,
    ImportStatus,
)
from budgeting.models import LegacyImportRun
from budgeting.services.import_legacy import (
    LegacyCatalogImporter,
)
from budgeting.services.legacy_bridge import (
    LegacyBudgetingClient,
)


class Command(BaseCommand):
    help = (
        "Importa etapas de orçamento, unidades de medida, "
        "grupos de materiais, insumos e composições "
        "históricas do Access para o PostgreSQL."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--initial",
            action="store_true",
            help="Confirma a execução da carga inicial.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help=("Permite repetir uma carga inicial já concluída."),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Lê e valida sem persistir.",
        )
        parser.add_argument(
            "--progress-every",
            type=int,
            default=250,
            help=("Exibe o progresso a cada N registros (padrão: 250)."),
        )
        parser.add_argument(
            "--only",
            choices=(
                "all",
                "stage-catalog",
                "measurement-units",
                "material-groups",
                "supplies",
                "compositions",
                "composition-items",
            ),
            default="all",
            help="Restringe o recurso importado.",
        )

    def handle(self, *args, **options):
        if not options["initial"]:
            raise CommandError("Use --initial para confirmar a carga inicial.")

        completed = LegacyImportRun.objects.filter(
            resource=ImportResource.LEGACY_CATALOG,
            initial=True,
            status=ImportStatus.COMPLETED,
        ).exists()

        if completed and not options["force"] and not options["dry_run"]:
            raise CommandError(
                "A carga inicial já foi concluída. Use --force somente se necessário."
            )

        progress_every = options["progress_every"]

        if progress_every < 1:
            raise CommandError("--progress-every deve ser maior que zero.")

        dry_run = options["dry_run"]
        selected_resource = options["only"]
        run = None

        if not dry_run:
            run = LegacyImportRun.objects.create(
                resource=ImportResource.LEGACY_CATALOG,
                initial=True,
                status=ImportStatus.RUNNING,
            )

        def write_progress(message: str) -> None:
            self.stdout.write(message)
            self.stdout.flush()

        def page_request(
            resource: str,
            offset: int,
            limit: int,
        ) -> None:
            write_progress(
                f"Bridge: solicitando {resource} (offset={offset}, limit={limit})..."
            )

        def page_response(
            resource: str,
            offset: int,
            count: int,
            has_more: bool,
        ) -> None:
            continuation = "sim" if has_more else "não"

            write_progress(
                f"Bridge: {resource} retornou "
                f"{count} registros "
                f"(offset={offset}, "
                f"possui próxima página={continuation})."
            )

        def import_progress(
            resource: str,
            result,
        ) -> None:
            if result.read > 0 and result.read % progress_every == 0:
                write_progress(
                    f"Processando {resource}: {result.read} registros lidos..."
                )

        client = LegacyBudgetingClient(
            on_page_request=page_request,
            on_page_response=page_response,
        )

        importer = LegacyCatalogImporter(
            client,
            progress_callback=import_progress,
        )

        counters: dict = {}
        errors: list[str] = []

        def execute_import(
            *,
            option: str,
            counter_key: str,
            label: str,
            callback,
        ) -> None:
            if selected_resource not in {"all", option}:
                return

            write_progress(f"Iniciando processamento de {label}...")

            result = callback(dry_run=dry_run)
            counters[counter_key] = result.as_dict()
            errors.extend(result.errors)

            write_progress(f"{label.capitalize()} finalizados: {result.as_dict()}")

        try:
            execute_import(
                option="stage-catalog",
                counter_key="stage_catalog",
                label="etapas de orçamento",
                callback=importer.import_stage_catalog,
            )

            # Catálogos de referência devem ser importados
            # antes dos insumos e composições.
            execute_import(
                option="measurement-units",
                counter_key="measurement_units",
                label="unidades de medida",
                callback=importer.import_measurement_units,
            )

            execute_import(
                option="material-groups",
                counter_key="material_groups",
                label="grupos de materiais",
                callback=importer.import_material_groups,
            )

            execute_import(
                option="supplies",
                counter_key="supplies",
                label="insumos",
                callback=importer.import_supplies,
            )

            execute_import(
                option="compositions",
                counter_key="compositions",
                label="composições",
                callback=importer.import_compositions,
            )

            execute_import(
                option="composition-items",
                counter_key="composition_items",
                label="itens das composições",
                callback=importer.import_composition_items,
            )

        except Exception as error:
            if run:
                run.status = ImportStatus.FAILED
                run.finished_at = timezone.now()
                run.counters = counters
                run.errors = [
                    str(error),
                    *errors[:99],
                ]
                run.save(
                    update_fields=(
                        "status",
                        "finished_at",
                        "counters",
                        "errors",
                    )
                )

            raise CommandError(str(error)) from error

        if run:
            run.status = ImportStatus.COMPLETED
            run.finished_at = timezone.now()
            run.counters = counters
            run.errors = errors[:100]
            run.save(
                update_fields=(
                    "status",
                    "finished_at",
                    "counters",
                    "errors",
                )
            )

        mode = "SIMULAÇÃO" if dry_run else "CONCLUÍDA"

        self.stdout.write(self.style.SUCCESS(f"Carga {mode}: {counters}"))

        if errors:
            self.stdout.write(self.style.WARNING(f"Registros ignorados: {len(errors)}"))
