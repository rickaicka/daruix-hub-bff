from django.core.management.base import BaseCommand

from accounts.models import HubModule, Permission


HUB_MODULES = [
    {
        "slug": "dashboard",
        "name": "Dashboard",
        "route": "/dashboard",
        "icon": "dashboard",
        "permission_code": "dashboard.ver",
        "desktop_enabled": True,
        "mobile_enabled": True,
        "mfe_enabled": False,
        "legacy_enabled": False,
        "remote_name": "",
        "remote_entry": "",
        "exposed_module": "",
        "order": 1,
    },
    {
        "slug": "proposta",
        "name": "Propostas",
        "route": "/propostas",
        "icon": "description",
        "permission_code": "proposta.ver",
        "desktop_enabled": True,
        "mobile_enabled": True,
        "mfe_enabled": True,
        "legacy_enabled": False,
        "remote_name": "propostas",
        "remote_entry": "http://localhost:4301/remoteEntry.js",
        "exposed_module": "./Routes",
        "order": 2,
    },
    {
        "slug": "po",
        "name": "Planilha de Orçamento",
        "route": "/planilhas-orcamento",
        "icon": "request_quote",
        "permission_code": "po.ver",
        "desktop_enabled": True,
        "mobile_enabled": True,
        "mfe_enabled": True,
        "legacy_enabled": False,
        "remote_name": "planilhasOrcamento",
        "remote_entry": "http://localhost:4302/remoteEntry.js",
        "exposed_module": "./Routes",
        "order": 3,
    },
    {
        "slug": "obra",
        "name": "Obras",
        "route": "/obras",
        "icon": "engineering",
        "permission_code": "obra.ver",
        "desktop_enabled": True,
        "mobile_enabled": True,
        "mfe_enabled": True,
        "legacy_enabled": False,
        "remote_name": "obras",
        "remote_entry": "http://localhost:4303/remoteEntry.js",
        "exposed_module": "./Routes",
        "order": 4,
    },
    {
        "slug": "financeiro",
        "name": "Financeiro",
        "route": "/financeiro",
        "icon": "payments",
        "permission_code": "financeiro.ver",
        "desktop_enabled": True,
        "mobile_enabled": True,
        "mfe_enabled": True,
        "legacy_enabled": False,
        "remote_name": "financeiro",
        "remote_entry": "http://localhost:4304/remoteEntry.js",
        "exposed_module": "./Routes",
        "order": 5,
    },
    {
        "slug": "relatorio",
        "name": "Relatórios",
        "route": "/relatorios",
        "icon": "bar_chart",
        "permission_code": "relatorio.ver",
        "desktop_enabled": True,
        "mobile_enabled": True,
        "mfe_enabled": True,
        "legacy_enabled": False,
        "remote_name": "relatorios",
        "remote_entry": "http://localhost:4305/remoteEntry.js",
        "exposed_module": "./Routes",
        "order": 6,
    },
    {
        "slug": "admin",
        "name": "Administração",
        "route": "/admin",
        "icon": "admin_panel_settings",
        "permission_code": "admin.ver",
        "desktop_enabled": True,
        "mobile_enabled": False,
        "mfe_enabled": True,
        "legacy_enabled": False,
        "remote_name": "admin",
        "remote_entry": "http://localhost:4306/remoteEntry.js",
        "exposed_module": "./Routes",
        "order": 99,
    },
]


class Command(BaseCommand):
    help = "Seeds Daruix Hub modules."

    def handle(self, *args, **options):
        for module_data in HUB_MODULES:
            data = module_data.copy()
            permission_code = data.pop("permission_code")

            permission = Permission.objects.filter(
                code=permission_code,
                is_active=True,
            ).first()

            if not permission:
                self.stdout.write(
                    self.style.WARNING(
                        f"Permission not found for module "
                        f"{data['slug']}: {permission_code}"
                    )
                )
                continue

            module, created = HubModule.objects.update_or_create(
                slug=data["slug"],
                defaults={
                    **data,
                    "permission": permission,
                    "is_active": True,
                },
            )

            action = "Created" if created else "Updated"

            self.stdout.write(
                self.style.SUCCESS(
                    f"{action} module: {module.slug}"
                )
            )

        self.stdout.write(
            self.style.SUCCESS("Daruix Hub modules seeded successfully.")
        )