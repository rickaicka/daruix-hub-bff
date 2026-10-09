# Refatoração do BFF e integração com o Legacy Bridge

## Escopo

Esta entrega preserva as URLs e os campos públicos existentes e corrige os
principais problemas encontrados no módulo de orçamentos:

- filtros e ordenação do DRF passam a ser configurados explicitamente;
- a listagem de insumos passa a ser paginada;
- o autocomplete usa paginação incremental para permitir scroll infinito;
- a classe duplicada `SupplyTypeViewSet` foi removida;
- o soft delete de registros HUB foi centralizado;
- registros legados continuam imutáveis;
- composições carregam somente a versão mais recente e evitam N+1;
- referências circulares entre subcomposições são rejeitadas;
- constraints protegem referências e valores dos itens;
- grupos diferentes com o mesmo ID legado deixam de ser sobrescritos;
- referências ao campo removido `Supply.code` foram eliminadas;
- configurações duplicadas do Legacy Bridge foram consolidadas;
- o transporte HTTP e a paginação do Legacy Bridge foram centralizados em
  `integrations.legacy_bridge`;
- o adaptador de `budgeting` preserva sua exceção de domínio e delega o HTTP
  ao cliente compartilhado;
- o schema OpenAPI reconhece a autenticação JWT customizada;
- os schemas dos apps `accounts` e `memorando_remessas` foram explicitados;
- o `entrypoint.sh` aceita o comando do Compose e manté o Gunicorn como
  fallback de produção;
- `requirements.txt`, `requirements.prod.txt` e
  `requirements-access.txt` foram normalizados para UTF-8;
- `runserver.bat` aceita opcionalmente o endereço e a porta.

## Alteração de contrato intencional

`GET /api/budgeting/supplies/` agora é paginado:

```json
{
  "count": 100,
  "next": "...",
  "previous": null,
  "results": []
}
```

O tamanho padrão é 25, aceita `page_size` e possui limite máximo de 100.

O autocomplete retorna 20 itens por página, aceita `page` e `page_size` e
limita cada página a 50 itens:

```text
GET /api/budgeting/supplies/autocomplete/?search=metal&page=1&page_size=20
```

```json
{
  "count": 222,
  "next": "...page=2&page_size=20",
  "previous": null,
  "results": []
}
```

## Aplicação

Antes de aplicar a migration, faça backup do PostgreSQL. Extraia o pacote de
alterações na raiz do repositório, preservando a estrutura de diretórios.

No PowerShell:

```powershell
docker compose -f .\docker-compose.local.yml up -d --build --force-recreate bff
docker compose -f .\docker-compose.local.yml exec bff python manage.py check
docker compose -f .\docker-compose.local.yml exec bff python manage.py showmigrations budgeting
docker compose -f .\docker-compose.local.yml exec bff python manage.py test budgeting
```

O `entrypoint.sh` executa `migrate` e `collectstatic` por padrão. Para desligar
esses passos em algum ambiente, configure `RUN_MIGRATIONS=0` ou
`COLLECT_STATIC=0`.

Quando o Compose fornece um `command`, ele é executado após a preparação. Sem
um comando, o entrypoint inicia o Gunicorn em `0.0.0.0:8000`.

## Dependências dos arquivos complementares

Os apps `memorando_remessas` e `integrations` foram avaliados junto com o
projeto. Eles não exigem novas dependências no `requirements.txt` principal:

- o cliente compartilhado do Legacy Bridge usa `urllib`, da biblioteca padrão;
- Django, DRF, `django-filter`, `drf-spectacular`, `pyodbc`,
  `python-decouple` e `reportlab` já estavam declarados;
- `requirements-access.txt` foi mantido separado, pois representa o ambiente
  das rotinas auxiliares do Access e não o runtime do BFF.

Os arquivos `tabelas-filtradas.txt` e `C_Subreqmat-Continuacao.txt` são
referências de consultas/tabelas do Access. Nenhum módulo Python os importa em
tempo de execução, portanto eles não alteram a instalação do BFF.

## Migration nova

`budgeting/migrations/0008_budgeting_integrity_and_indexes.py`:

- permite IDs legados repetidos em grupos com nomes diferentes;
- mantém única a combinação `(legacy_id, nome)`;
- adiciona índices para as listagens ativas;
- impede referências incompatíveis com o tipo do item;
- impede coeficientes e preços negativos.

## Validação executada

- `python -m compileall`: aprovado;
- `manage.py check`: aprovado com todos os apps enviados;
- `makemigrations --check --dry-run`: nenhuma alteração pendente;
- 20 testes de `budgeting` e `integrations`: aprovados;
- geração e validação do OpenAPI: aprovada sem warnings.
