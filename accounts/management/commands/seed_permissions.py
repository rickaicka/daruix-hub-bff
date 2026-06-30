from django.core.management.base import BaseCommand

from accounts.models import GroupPermission, Permission, UserGroup
from accounts.models.choices import ClientGroup, EmployeeGroup, UserType


PERMISSIONS = [
    # Dashboard
    ("dashboard.ver", "dashboard", "Visualizar dashboard"),

    # Propostas
    ("proposta.ver", "proposta", "Visualizar propostas"),
    ("proposta.criar", "proposta", "Criar propostas"),
    ("proposta.editar", "proposta", "Editar propostas"),
    ("proposta.excluir", "proposta", "Excluir propostas"),
    ("proposta.aprovar", "proposta", "Aprovar propostas"),

    # Planilha de orçamento
    ("po.ver", "po", "Visualizar planilha de orçamento"),
    ("po.criar", "po", "Criar planilha de orçamento"),
    ("po.editar", "po", "Editar planilha de orçamento"),
    ("po.excluir", "po", "Excluir planilha de orçamento"),
    ("po.aprovar", "po", "Aprovar planilha de orçamento"),

    # Obras
    ("obra.ver", "obra", "Visualizar obras"),
    ("obra.criar", "obra", "Criar obras"),
    ("obra.editar", "obra", "Editar obras"),
    ("obra.excluir", "obra", "Excluir obras"),

    # Financeiro
    ("financeiro.ver", "financeiro", "Visualizar financeiro"),
    ("financeiro.contas_pagar.ver", "financeiro", "Visualizar contas a pagar"),
    ("financeiro.contas_pagar.criar", "financeiro", "Criar contas a pagar"),
    ("financeiro.contas_pagar.editar", "financeiro", "Editar contas a pagar"),

    ("financeiro.op.ver", "financeiro", "Visualizar ordens de pagamento"),
    ("financeiro.op.criar", "financeiro", "Criar ordens de pagamento"),
    ("financeiro.op.aprovar", "financeiro", "Aprovar ordens de pagamento"),
    ("financeiro.op.pagar", "financeiro", "Registrar pagamento de OP"),

    # Relatórios
    ("relatorio.ver", "relatorio", "Visualizar relatórios"),
    ("relatorio.executivo.ver", "relatorio", "Visualizar relatórios executivos"),

    # Administração
    ("admin.ver", "admin", "Visualizar administração"),
    ("admin.usuarios.ver", "admin", "Visualizar usuários"),
    ("admin.usuarios.criar", "admin", "Criar usuários"),
    ("admin.usuarios.editar", "admin", "Editar usuários"),
    ("admin.usuarios.desativar", "admin", "Desativar usuários"),

    ("admin.permissoes.ver", "admin", "Visualizar permissões"),
    ("admin.permissoes.editar", "admin", "Editar permissões"),
]


EMPLOYEE_GROUP_PERMISSION_MAP = {
    EmployeeGroup.BOARD: [
        "dashboard.ver",

        "proposta.ver",
        "proposta.criar",
        "proposta.editar",
        "proposta.excluir",
        "proposta.aprovar",

        "po.ver",
        "po.criar",
        "po.editar",
        "po.excluir",
        "po.aprovar",

        "obra.ver",
        "obra.criar",
        "obra.editar",
        "obra.excluir",

        "financeiro.ver",
        "financeiro.contas_pagar.ver",
        "financeiro.contas_pagar.criar",
        "financeiro.contas_pagar.editar",
        "financeiro.op.ver",
        "financeiro.op.criar",
        "financeiro.op.aprovar",
        "financeiro.op.pagar",

        "relatorio.ver",
        "relatorio.executivo.ver",

        "admin.ver",
        "admin.usuarios.ver",
        "admin.usuarios.criar",
        "admin.usuarios.editar",
        "admin.usuarios.desativar",
        "admin.permissoes.ver",
        "admin.permissoes.editar",
    ],

    EmployeeGroup.ADMINISTRATIVE: [
        "dashboard.ver",

        "proposta.ver",
        "po.ver",
        "obra.ver",

        "financeiro.ver",
        "financeiro.contas_pagar.ver",
        "financeiro.op.ver",

        "relatorio.ver",

        "admin.ver",
        "admin.usuarios.ver",
    ],

    EmployeeGroup.ENGINEERING: [
        "dashboard.ver",

        "proposta.ver",
        "proposta.criar",
        "proposta.editar",

        "po.ver",
        "po.criar",
        "po.editar",

        "obra.ver",
        "obra.criar",
        "obra.editar",

        "relatorio.ver",
    ],

    EmployeeGroup.WORKS: [
        "dashboard.ver",

        "po.ver",
        "obra.ver",
        "obra.editar",

        "relatorio.ver",
    ],

    EmployeeGroup.FINANCIAL: [
        "dashboard.ver",

        "financeiro.ver",
        "financeiro.contas_pagar.ver",
        "financeiro.contas_pagar.criar",
        "financeiro.contas_pagar.editar",
        "financeiro.op.ver",
        "financeiro.op.criar",
        "financeiro.op.aprovar",
        "financeiro.op.pagar",

        "relatorio.ver",
    ],

    EmployeeGroup.PURCHASES: [
        "dashboard.ver",

        "po.ver",
        "po.criar",
        "po.editar",

        "obra.ver",

        "financeiro.op.ver",
    ],
}


CLIENT_GROUP_PERMISSION_MAP = {
    ClientGroup.BOARD: [
        "dashboard.ver",
        "proposta.ver",
        "obra.ver",
        "relatorio.ver",
        "relatorio.executivo.ver",
    ],

    ClientGroup.OPERATIONAL: [
        "proposta.ver",
        "obra.ver",
        "relatorio.ver",
    ],
}


SUPPLIER_GROUP_PERMISSION_MAP = {
    "PADRAO": [
        "dashboard.ver",
    ],
}


class Command(BaseCommand):
    help = "Seeds SGOWEB default groups and permissions."

    def handle(self, *args, **options):
        permissions_by_code = self._seed_permissions()

        self._seed_group_permissions(
            user_type=UserType.EMPLOYEE,
            group_permission_map=EMPLOYEE_GROUP_PERMISSION_MAP,
            permissions_by_code=permissions_by_code,
            description_suffix="de colaboradores",
        )

        self._seed_group_permissions(
            user_type=UserType.CLIENT,
            group_permission_map=CLIENT_GROUP_PERMISSION_MAP,
            permissions_by_code=permissions_by_code,
            description_suffix="de clientes",
        )

        self._seed_group_permissions(
            user_type=UserType.SUPPLIER,
            group_permission_map=SUPPLIER_GROUP_PERMISSION_MAP,
            permissions_by_code=permissions_by_code,
            description_suffix="de fornecedores",
        )

        self.stdout.write(
            self.style.SUCCESS("SGOWEB permissions seeded successfully.")
        )

    def _seed_permissions(self):
        permissions_by_code = {}

        for code, module, description in PERMISSIONS:
            permission, _ = Permission.objects.update_or_create(
                code=code,
                defaults={
                    "module": module,
                    "description": description,
                    "is_active": True,
                },
            )

            permissions_by_code[code] = permission

        return permissions_by_code

    def _seed_group_permissions(
        self,
        user_type,
        group_permission_map,
        permissions_by_code,
        description_suffix,
    ):
        for group_name, permission_codes in group_permission_map.items():
            group_label = self._get_group_label(group_name)
            group_value = self._get_group_value(group_name)

            group, _ = UserGroup.objects.update_or_create(
                user_type=user_type,
                name=group_value,
                defaults={
                    "description": f"Grupo {group_label} {description_suffix}.",
                    "is_active": True,
                },
            )

            for permission_code in permission_codes:
                permission = permissions_by_code.get(permission_code)

                if not permission:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Permission not found: {permission_code}"
                        )
                    )
                    continue

                GroupPermission.objects.update_or_create(
                    group=group,
                    permission=permission,
                    defaults={
                        "is_active": True,
                    },
                )

    def _get_group_value(self, group_name):
        if hasattr(group_name, "value"):
            return group_name.value

        return str(group_name)

    def _get_group_label(self, group_name):
        if hasattr(group_name, "label"):
            return group_name.label

        return str(group_name).title()