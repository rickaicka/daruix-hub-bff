from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import HubModule, Permission


PERMISSIONS = [
    {
        "code": "shipment_memo.view",
        "description": "Visualizar memorandos de remessa.",
    },
    {
        "code": "shipment_memo.create",
        "description": "Criar memorandos de remessa.",
    },
    {
        "code": "shipment_memo.update",
        "description": "Alterar memorandos de remessa em rascunho.",
    },
    {
        "code": "shipment_memo.send",
        "description": "Enviar e finalizar memorandos de remessa.",
    },
    {
        "code": "shipment_memo.cancel",
        "description": "Cancelar memorandos de remessa.",
    },
    {
        "code": "shipment_memo.delete",
        "description": "Excluir memorandos de remessa em rascunho.",
    },
    {
        "code": "shipment_memo.manage_options",
        "description": (
            "Cadastrar e administrar opções de espécie, "
            "finalidade e solicitação."
        ),
    },
    {
        "code": "shipment_memo.be_responsible",
        "description": (
            "Permitir que o usuário seja selecionado como "
            "responsável por memorandos de remessa."
        ),
    },
]


class Command(BaseCommand):
    help = (
        "Cria ou atualiza permissões e o módulo "
        "de Memorandos de Remessa."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        permission_map = {}

        created_permissions = 0
        updated_permissions = 0

        for permission_data in PERMISSIONS:
            permission, created = Permission.objects.update_or_create(
                code=permission_data["code"],
                defaults={
                    "module": "shipment_memo",
                    "description": permission_data["description"],
                    "is_active": True,
                },
            )

            permission_map[permission.code] = permission

            if created:
                created_permissions += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Permissão criada: {permission.code}"
                    )
                )
            else:
                updated_permissions += 1

                self.stdout.write(
                    self.style.WARNING(
                        f"Permissão atualizada: {permission.code}"
                    )
                )

        view_permission = permission_map["shipment_memo.view"]

        hub_module, module_created = HubModule.objects.update_or_create(
            slug="memorando-remessas",
            defaults={
                "name": "Memorando de Remessas",
                "route": "/memorando-remessas",
                "icon": "file-text",
                "permission": view_permission,
                "desktop_enabled": True,
                "mobile_enabled": True,
                "mfe_enabled": False,
                "legacy_enabled": False,
                "remote_name": "",
                "remote_entry": "",
                "exposed_module": "./Routes",
                "order": 10,
                "is_active": True,
            },
        )

        if module_created:
            self.stdout.write(
                self.style.SUCCESS(
                    "Módulo criado: Memorando de Remessas"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "Módulo atualizado: Memorando de Remessas"
                )
            )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "Seed de Memorandos de Remessa concluído."
            )
        )

        self.stdout.write(
            f"Permissões criadas: {created_permissions}"
        )

        self.stdout.write(
            f"Permissões atualizadas: {updated_permissions}"
        )

        self.stdout.write(
            f"ID do módulo: {hub_module.id}"
        )

        self.stdout.write(
            "Permissão mínima do módulo: shipment_memo.view"
        )