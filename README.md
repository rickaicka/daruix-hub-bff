Daruix Hub BFF
Backend-for-Frontend do Daruix Hub, responsável por autenticação, sessão JWT, permissões, módulos disponíveis no Hub e integração gradual com o sistema legado em Microsoft Access.
O projeto foi desenvolvido em Python + Django + Django REST Framework, servindo como camada intermediária entre o Hub Shell/MFEs e as fontes de dados internas da Daruix.
---
Visão geral
O `daruix-hub-bff` centraliza:
autenticação de usuários;
emissão de tokens JWT;
endpoint de usuário autenticado;
permissões por grupo;
cadastro de módulos do Hub;
exposição de módulos disponíveis para desktop/mobile/MFE/legado;
integração com base legada Microsoft Access durante a fase de migração;
documentação automática da API com Swagger/OpenAPI.
---
Stack principal
Python
Django 6
Django REST Framework
Simple JWT
PostgreSQL
pyodbc
Microsoft Access Driver
drf-spectacular
django-cors-headers
django-filter
python-decouple
---
Estrutura resumida
```txt
daruix-hub-bff/
├─ accounts/
│  ├─ models/
│  │  ├─ user.py
│  │  ├─ user_group.py
│  │  ├─ permission.py
│  │  ├─ hub_module.py
│  │  ├─ client.py
│  │  ├─ employee.py
│  │  ├─ supplier.py
│  │  └─ choices.py
│  ├─ serializers/
│  │  ├─ auth.py
│  │  ├─ hub_module_serializer.py
│  │  └─ permissioning.py
│  ├─ services/
│  ├─ urls.py
│  └─ views.py
│
├─ config/
│  ├─ settings.py
│  ├─ urls.py
│  ├─ wsgi.py
│  └─ asgi.py
│
├─ legacy_reader/
│  ├─ access_connection.py
│  ├─ access_mapper.py
│  ├─ auth_bridge.py
│  ├─ inspect_table.py
│  ├─ extract_groups.py
│  └─ extract_legacy_structure.py
│
├─ manage.py
├─ requirements.txt
└─ .env
```
---
Conceitos de domínio
Usuários
O sistema usa um model customizado de usuário em `accounts.User`.
Cada usuário possui:
`id_usuario`
`username`
`nome`
`email`
`tipo_usuario`
`grupo`
origem do usuário
informações de migração do Access
flags administrativas
dados de acesso ao legado
Tipos principais:
```txt
CLIENTE
COLABORADOR
FORNECEDOR
```
Perfis complementares
Dependendo do tipo de usuário, existem modelos complementares:
`Client`
`Employee`
`Supplier`
Esses modelos validam se o usuário associado pertence ao tipo correto.
Grupos
Os grupos ficam em `UserGroup` e são separados por tipo de usuário.
Exemplo:
```txt
COLABORADOR | DIRETORIA
COLABORADOR | FINANCEIRO
CLIENTE | OPERACIONAL
```
Permissões
As permissões ficam no model `Permission`.
Exemplo de códigos:
```txt
dashboard.ver
obra.ver
obra.criar
financeiro.ver
financeiro.op.aprovar
admin.usuarios.editar
```
A relação entre grupo e permissão é feita por `GroupPermission`.
Módulos do Hub
Os módulos ficam em `HubModule`.
Cada módulo pode definir:
nome
slug
rota
ícone
permissão mínima
se aparece no desktop
se aparece no mobile
se é MFE
se é legado
configuração de remote module
Exemplo de payload retornado ao front:
```json
{
  "slug": "financeiro",
  "nome": "Financeiro",
  "rota": "/financeiro",
  "icone": "payments",
  "permissao": "financeiro.ver",
  "desktop_enabled": true,
  "mobile_enabled": true,
  "mfe_enabled": true,
  "legacy_enabled": false,
  "remote": {
    "remote_name": "financeiro",
    "remote_entry": "http://localhost:4304/remoteEntry.js",
    "exposed_module": "./Routes"
  }
}
```
---
Autenticação
O projeto usa JWT com `djangorestframework_simplejwt`.
Login
Endpoint esperado:
```http
POST /api/auth/login
```
Body:
```json
{
  "username": "renato",
  "password": "123456"
}
```
Resposta:
```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer",
  "usuario": {
    "id_usuario": 2,
    "username": "renato",
    "nome": "Renato Salim Daruix",
    "email": "renato@legacy.local",
    "tipo_usuario": "COLABORADOR",
    "grupo": "DIRETORIA",
    "permissoes": [],
    "modulos": []
  }
}
```
O retorno do login já contém as permissões e módulos necessários para o Hub Shell e MFEs.
Usuário autenticado
Endpoint esperado:
```http
GET /api/auth/me
```
Uso recomendado:
validar sessão ao recarregar a página;
atualizar permissões;
atualizar módulos;
confirmar token salvo no front.
Logout
Endpoint esperado:
```http
POST /api/auth/logout
```
Body:
```json
{
  "refresh_token": "..."
}
```
---
Integração com Microsoft Access legado
Durante a fase de migração, o BFF pode autenticar usuários no Access.
A integração usa:
`pyodbc`
`Microsoft Access Driver (*.mdb, *.accdb)`
caminho da base definido por `LEGACY_DB_PATH`
bridge isolada em `legacy_reader/auth_bridge.py`
conexão via `legacy_reader/access_connection.py`
Variáveis relacionadas
```env
LEGACY_AUTH_ENABLED=True
LEGACY_DB_PATH=D:\Projects\SGO_be.accdb
LEGACY_PYTHON_PATH=D:\Projects\Daruix\daruix-hub-bff\.venv32\Scripts\python.exe
LEGACY_AUTH_BRIDGE_PATH=D:\Projects\Daruix\daruix-hub-bff\legacy_reader\auth_bridge.py
```
Observação sobre ambiente 32-bit
Em ambientes Windows, o driver do Access pode exigir Python/venv 32-bit, dependendo da versão instalada do Microsoft Access Database Engine.
---
Configuração local
1. Criar ambiente virtual
```powershell
cd D:\Projects\Daruix\daruix-hub-bff
python -m venv .venv
.\.venv\Scripts\activate
```
2. Instalar dependências
```powershell
pip install -r requirements.txt
```
3. Criar `.env`
Crie um arquivo `.env` na raiz:
```env
DEBUG=True
DATABASE_URL=postgresql://postgres:admin@localhost:5432/sgo-daruix-web
ALLOWED_HOSTS=localhost,127.0.0.1

SECRET_KEY=troque-essa-chave-em-dev

LEGACY_AUTH_ENABLED=True
LEGACY_DB_PATH=D:\Projects\SGO_be.accdb
LEGACY_PYTHON_PATH=D:\Projects\Daruix\daruix-hub-bff\.venv32\Scripts\python.exe
LEGACY_AUTH_BRIDGE_PATH=D:\Projects\Daruix\daruix-hub-bff\legacy_reader\auth_bridge.py
```
> Nunca commitar `.env` real com `SECRET_KEY`, caminhos internos sensíveis ou credenciais.
4. Rodar migrations
```powershell
python manage.py makemigrations
python manage.py migrate
```
5. Criar superusuário
```powershell
python manage.py createsuperuser
```
6. Subir servidor local
```powershell
python manage.py runserver 8080
```
API local:
```txt
http://localhost:8080/api/
```
Admin:
```txt
http://localhost:8080/admin/
```
Swagger:
```txt
http://localhost:8080/api/docs/
```
Redoc:
```txt
http://localhost:8080/api/redoc/
```
Schema OpenAPI:
```txt
http://localhost:8080/api/schema/
```
---
CORS
Origens locais configuradas:
```txt
http://localhost:4200
http://localhost:8100
http://localhost:4300
http://127.0.0.1:4300
http://192.168.0.73:4300
```
Essas portas atendem o Hub Shell, Ionic e MFEs em desenvolvimento.
---
Testes e scripts úteis do legado
Inspecionar tabela do Access
```powershell
python legacy_reader\inspect_table.py "tblUsuario"
```
Procurar usuário no Access
```powershell
python legacy_reader\find_user.py renato
```
Debug de senha
```powershell
python legacy_reader\check_password_debug.py --username renato --password 123456
```
Extrair grupos
```powershell
python legacy_reader\extract_groups.py
```
Extrair estrutura legada
```powershell
python legacy_reader\extract_legacy_structure.py
```
---
Fluxo esperado com o Hub Shell
```txt
Hub Shell
├─ POST /api/auth/login
├─ recebe access_token, refresh_token e usuario
├─ salva sessão via @daruix/hub-auth
├─ monta menu com usuario.modulos
├─ valida botões/telas com usuario.permissoes
└─ carrega MFEs quando módulo tiver mfe_enabled = true
```
---
Payload usado pelo front
O front espera que `usuario` tenha este formato:
```ts
export interface HubUser {
  id_usuario: number;
  username: string;
  nome: string;
  email: string;
  tipo_usuario: string;
  grupo: string | null;
  permissoes: string[];
  modulos: HubModulo[];
  origem: string;
  ativo: boolean;
  is_staff: boolean;
  is_superuser: boolean;
}
```
E módulos:
```ts
export interface HubModulo {
  slug: string;
  nome: string;
  rota: string;
  icone: string;
  permissao: string;
  desktop_enabled: boolean;
  mobile_enabled: boolean;
  mfe_enabled: boolean;
  legacy_enabled: boolean;
  remote: HubRemoteModule | null;
}
```
---
Segurança
Não commitar `.env` real.
Rotacionar `SECRET_KEY` caso ela tenha sido exposta.
Não confiar apenas nas permissões do frontend.
Toda ação crítica deve validar permissões no backend.
Tokens devem trafegar somente em HTTPS em produção.
O Access deve ser tratado como fonte transitória durante migração.
---
Roadmap sugerido
Centralizar políticas de permissão por módulo.
Criar seeds/fixtures para módulos e permissões base.
Separar autenticação legacy de autenticação Django.
Melhorar auditoria de login e sincronização.
Adicionar testes automatizados para login, permissões e módulos.
Criar comandos Django para sincronização controlada com Access.
Preparar Dockerfile e docker-compose para ambiente local padronizado.
---
Repositórios relacionados
`daruix-hub-shell`: Shell Angular/Ionic do Daruix Hub.
`daruix-hub-auth`: pacote compartilhado de sessão/auth para Shell e MFEs.
`mfe-memorando-remessa`: primeiro MFE do Hub.
`daruix-ds`: Design System Daruix.
`daruix-site-front`: site institucional.