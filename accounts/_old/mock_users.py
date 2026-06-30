MOCK_USERS = {
    'admin@daruix.com.br': {
        'id': 1,
        'password': '123456',
        'name': 'Administrador Daruix',
        'email': 'admin@daruix.com.br',
        'role': 'admin',
        'apps': [
            'remessas',
            'admin',
        ],
        'permissions': [
            'hub.access',
            'remessas.access',
            'remessas.view',
            'remessas.import',
            'remessas.export',
            'remessas.delete',
            'admin.access',
            'admin.users.manage',
        ],
    },

    'funcionario@daruix.com.br': {
        'id': 2,
        'password': '123456',
        'name': 'Funcionário Daruix',
        'email': 'funcionario@daruix.com.br',
        'role': 'funcionario',
        'apps': [
            'remessas',
        ],
        'permissions': [
            'hub.access',
            'remessas.access',
            'remessas.view',
        ],
    },

    'importador@daruix.com.br': {
        'id': 3,
        'password': '123456',
        'name': 'Importador Daruix',
        'email': 'importador@daruix.com.br',
        'role': 'operador',
        'apps': [
            'remessas',
        ],
        'permissions': [
            'hub.access',
            'remessas.access',
            'remessas.view',
            'remessas.import',
            'remessas.export',
        ],
    },
}