import json
from pathlib import Path

from django.core.management.base import BaseCommand

from accounts.models import (
    GroupPermission,
    HubModule,
    PermissionCode,
    UserGroup,
    UserType,
)


GROUP_ACTIONS = {
    "administrador": [
        "view",
        "create",
        "update",
        "delete",
        "export",
        "manage",
    ],
    "diretoria": [
        "view",
        "create",
        "update",
        "delete",
        "export",
        "approve",
    ],
    "obras": [
        "view",
        "create",
        "update",
    ],
    "arquitetura": [
        "view",
        "create",
        "update",
    ],
    "planejamento": [
        "view",
        "create",
        "update",
        "export",
    ],
    "suprimentos": [
        "view",
        "create",
        "update",
        "export",
    ],
    "rh": [
        "view",
        "create",
        "update",
    ],
}


ACTION_NAMES = {
    "view": "Visualizar",
    "create": "Criar",
    "update": "Alterar",
    "delete": "Excluir",
    "export": "Exportar",
    "approve": "Aprovar",
    "manage": "Gerenciar",
}


IGNORED_MODULES = {
    "sair",
    "teste",
    "bkp",
}


class Command(BaseCommand):
    help = "Importa tipos, grupos, módulos e permissões extraídos do Access."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default="legacy_reader/legacy_structure.json",
            help="Caminho do JSON exportado do Access.",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"])

        if not file_path.exists():
            self.stderr.write(
                self.style.ERROR(f"Arquivo não encontrado: {file_path}")
            )
            return

        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        user_type = self.import_user_type(data["user_type"])
        groups = self.import_groups(user_type, data.get("groups", []))
        modules = self.import_modules(user_type, data.get("modules", []))

        self.import_permissions(user_type, groups, modules)

        self.stdout.write(
            self.style.SUCCESS("Estrutura legada importada com sucesso.")
        )

    def import_user_type(self, user_type_data):
        user_type, created = UserType.objects.update_or_create(
            slug=user_type_data["slug"],
            defaults={
                "name": user_type_data["name"],
                "legacy_name": user_type_data["name"],
            },
        )

        self.stdout.write(
            f"{'Criado' if created else 'Atualizado'} UserType: {user_type}"
        )

        return user_type

    def import_groups(self, user_type, groups_data):
        groups = {}

        for group_data in groups_data:
            group, created = UserGroup.objects.update_or_create(
                user_type=user_type,
                slug=group_data["slug"],
                defaults={
                    "name": group_data["name"],
                    "legacy_name": group_data.get("legacy_name", ""),
                },
            )

            groups[group.slug] = group

            self.stdout.write(
                f"{'Criado' if created else 'Atualizado'} grupo: {group}"
            )

        return groups

    def import_modules(self, user_type, modules_data):
        modules = {}

        order = 1

        for module_data in modules_data:
            slug = module_data["slug"]

            if slug in IGNORED_MODULES:
                continue

            module, created = HubModule.objects.update_or_create(
                user_type=user_type,
                slug=slug,
                defaults={
                    "name": module_data["name"],
                    "description": (
                        f"Módulo importado do Access: "
                        f"{module_data.get('source_table', '')}"
                    ),
                    "route": f"/{slug.replace('_', '-')}",
                    "icon": "folder",
                    "desktop_enabled": True,
                    "mobile_enabled": True,
                    "legacy_enabled": True,
                    "order": order,
                    "is_active": True,
                    "legacy_object_name": module_data.get("legacy_name", ""),
                },
            )

            modules[module.slug] = module
            order += 1

            self.stdout.write(
                f"{'Criado' if created else 'Atualizado'} módulo: {module}"
            )

        return modules

    def import_permissions(self, user_type, groups, modules):
        for module in modules.values():
            permissions_by_action = {}

            all_actions = {
                action
                for actions in GROUP_ACTIONS.values()
                for action in actions
            }

            for action in all_actions:
                code = f"{user_type.slug}.{module.slug}.{action}"

                permission, created = PermissionCode.objects.update_or_create(
                    code=code,
                    defaults={
                        "module": module,
                        "name": ACTION_NAMES.get(action, action.title()),
                        "description": (
                            f"{ACTION_NAMES.get(action, action.title())} "
                            f"em {module.name}"
                        ),
                        "legacy_permission_name": action,
                    },
                )

                permissions_by_action[action] = permission

                self.stdout.write(
                    f"{'Criada' if created else 'Atualizada'} permissão: {code}"
                )

            for group_slug, actions in GROUP_ACTIONS.items():
                group = groups.get(group_slug)

                if not group:
                    continue

                for action in actions:
                    permission = permissions_by_action[action]

                    GroupPermission.objects.get_or_create(
                        group=group,
                        permission=permission,
                    )