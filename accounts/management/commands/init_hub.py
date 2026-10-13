"""Inicialização do catálogo de permissões e módulos do Hub, sem conceder acessos."""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from accounts.models import HubModule, Permission

# Catálogo dos seeds originais + permissão de entrada de Gestão Administrativa.
PERMISSIONS = [('dashboard.ver', 'dashboard', 'Visualizar dashboard'),
 ('proposta.ver', 'proposta', 'Visualizar propostas'),
 ('proposta.criar', 'proposta', 'Criar propostas'),
 ('proposta.editar', 'proposta', 'Editar propostas'),
 ('proposta.excluir', 'proposta', 'Excluir propostas'),
 ('proposta.aprovar', 'proposta', 'Aprovar propostas'),
 ('po.ver', 'po', 'Visualizar planilha de orçamento'),
 ('po.criar', 'po', 'Criar planilha de orçamento'),
 ('po.editar', 'po', 'Editar planilha de orçamento'),
 ('po.excluir', 'po', 'Excluir planilha de orçamento'),
 ('po.aprovar', 'po', 'Aprovar planilha de orçamento'),
 ('obra.ver', 'obra', 'Visualizar obras'),
 ('obra.criar', 'obra', 'Criar obras'),
 ('obra.editar', 'obra', 'Editar obras'),
 ('obra.excluir', 'obra', 'Excluir obras'),
 ('financeiro.ver', 'financeiro', 'Visualizar financeiro'),
 ('financeiro.contas_pagar.ver', 'financeiro', 'Visualizar contas a pagar'),
 ('financeiro.contas_pagar.criar', 'financeiro', 'Criar contas a pagar'),
 ('financeiro.contas_pagar.editar', 'financeiro', 'Editar contas a pagar'),
 ('financeiro.op.ver', 'financeiro', 'Visualizar ordens de pagamento'),
 ('financeiro.op.criar', 'financeiro', 'Criar ordens de pagamento'),
 ('financeiro.op.aprovar', 'financeiro', 'Aprovar ordens de pagamento'),
 ('financeiro.op.pagar', 'financeiro', 'Registrar pagamento de OP'),
 ('relatorio.ver', 'relatorio', 'Visualizar relatórios'),
 ('relatorio.executivo.ver', 'relatorio', 'Visualizar relatórios executivos'),
 ('admin.ver', 'admin', 'Visualizar administração'),
 ('admin.usuarios.ver', 'admin', 'Visualizar usuários'),
 ('admin.usuarios.criar', 'admin', 'Criar usuários'),
 ('admin.usuarios.editar', 'admin', 'Editar usuários'),
 ('admin.usuarios.desativar', 'admin', 'Desativar usuários'),
 ('admin.permissoes.ver', 'admin', 'Visualizar permissões'),
 ('admin.permissoes.editar', 'admin', 'Editar permissões'),
 ('shipment_memo.view', 'shipment_memo', 'Visualizar memorandos de remessa.'),
 ('shipment_memo.create', 'shipment_memo', 'Criar memorandos de remessa.'),
 ('shipment_memo.update', 'shipment_memo', 'Alterar memorandos de remessa em rascunho.'),
 ('shipment_memo.send', 'shipment_memo', 'Enviar e finalizar memorandos de remessa.'),
 ('shipment_memo.cancel', 'shipment_memo', 'Cancelar memorandos de remessa.'),
 ('shipment_memo.delete', 'shipment_memo', 'Excluir memorandos de remessa em rascunho.'),
 ('shipment_memo.manage_options',
  'shipment_memo',
  'Cadastrar e administrar opções de espécie, finalidade e solicitação.'),
 ('shipment_memo.be_responsible',
  'shipment_memo',
  'Permitir que o usuário seja selecionado como responsável por memorandos de remessa.'),
 ('cadastro.ver', 'cadastro', 'Acessar Gestão Administrativa no Hub.')]

MODULES = [{'slug': 'dashboard',
  'aliases': [],
  'name': 'Dashboard',
  'route': '/hub/dashboard',
  'icon': 'dashboard',
  'permission_code': 'dashboard.ver',
  'remote_name': '',
  'remote_entry': '',
  'order': 1},
 {'slug': 'memorando-remessas',
  'aliases': ['remessas'],
  'name': 'Memorando de Remessas',
  'route': '/hub/remessas',
  'icon': 'file-text',
  'permission_code': 'shipment_memo.view',
  'remote_name': 'remessas',
  'remote_entry': '/remotes/remessas/remoteEntry.json',
  'order': 2},
 {'slug': 'obra',
  'aliases': ['obras'],
  'name': 'Obras',
  'route': '/hub/obras',
  'icon': 'engineering',
  'permission_code': 'obra.ver',
  'remote_name': 'obras',
  'remote_entry': '/remotes/obras/remoteEntry.json',
  'order': 3},
 {'slug': 'gestao-administrativa',
  'aliases': ['cadastros'],
  'name': 'Gestão Administrativa',
  'route': '/hub/gestao-administrativa',
  'icon': 'settings',
  'permission_code': 'cadastro.ver',
  'remote_name': 'gestao-administrativa',
  'remote_entry': '/remotes/cadastros/remoteEntry.json',
  'order': 4}]

class Command(BaseCommand):
    help = "Inicializa permissões e módulos atuais; preserva registros existentes por padrão."
    requires_migrations_checks = True

    def add_arguments(self, parser):
        parser.add_argument('--atualizar', action='store_true',
                            help='Atualiza metadados dos registros do catálogo; preserva is_active e vínculos.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Executa em transação e desfaz as alterações ao final.')

    @transaction.atomic
    def handle(self, *args, **options):
        counts = {'criados': 0, 'atualizados': 0, 'preservados': 0}

        def persist(obj, created, defaults):
            if created:
                action = 'criados'
            elif options.get('atualizar'):
                changed = []
                for key, value in defaults.items():
                    if getattr(obj, key) != value:
                        setattr(obj, key, value)
                        changed.append(key)
                if changed:
                    # Não reativa cadastros desativados manualmente.
                    if hasattr(obj, 'updated_at'):
                        changed.append('updated_at')
                    obj.save(update_fields=changed)
                action = 'atualizados' if changed else 'preservados'
            else:
                action = 'preservados'
            counts[action] += 1
            self.stdout.write(f"{action}: {obj}")

        for code, module, description in PERMISSIONS:
            defaults = {'module': module, 'description': description}
            obj, created = Permission.objects.get_or_create(code=code, defaults=defaults)
            persist(obj, created, defaults)

        for item in MODULES:
            data = item.copy()
            slug = data.pop('slug')
            aliases = data.pop('aliases')
            permission_code = data.pop('permission_code')
            # Reutiliza IDs existentes e evita duplicar variantes históricas de slug.
            routes = [data['route'], data['route'].removeprefix('/hub')]
            if slug == 'memorando-remessas':
                routes.append('/memorando-remessas')
            matches = list(HubModule.objects.filter(
                Q(slug__in=[slug, *aliases]) | Q(route__in=routes)
            ).distinct())
            if len(matches) > 1:
                raise CommandError(
                    f"Mais de um módulo corresponde a {slug}: "
                    + ', '.join(str(obj.slug) for obj in matches)
                    + '. Revise os duplicados antes de inicializar. Transação desfeita.'
                )
            data.update({
                'permission': Permission.objects.get(code=permission_code),
                'mfe_enabled': bool(data['remote_name']),
                'legacy_enabled': False,
                'desktop_enabled': True,
                'mobile_enabled': True,
                'exposed_module': './Routes' if data['remote_name'] else '',
            })
            if matches:
                obj, created = matches[0], False
            else:
                obj, created = HubModule.objects.get_or_create(slug=slug, defaults=data)
            persist(obj, created, data)

        self.stdout.write(str(counts))
        self.stdout.write('Grupos, usuários, vínculos de acesso e menus não foram alterados.')
        if options.get('dry_run'):
            transaction.set_rollback(True)
            self.stdout.write(self.style.WARNING('Simulação concluída; alterações desfeitas.'))
        else:
            self.stdout.write(self.style.SUCCESS('Inicialização concluída.'))
