# Agente de IA para LinkedIn

Assistente de inteligência artificial para planejar e aprimorar uma presença profissional no LinkedIn. O projeto está sendo desenvolvido de forma incremental, com revisão humana para ações externas e uso exclusivo de integrações oficiais e autorizadas.

## Estado do projeto

Este repositório contém modelos e serviços de domínio para critérios de busca, perfil profissional e vagas, além de uma camada de persistência SQLAlchemy com migrations Alembic. A aplicação ainda não implementa FastAPI, autenticação, provedor de IA, API do LinkedIn, fluxo na nuvem ou recurso de publicação. O projeto não coleta dados do LinkedIn por scraping nem automatiza curtidas, comentários, conexões ou mensagens.

O acesso à API do LinkedIn depende das permissões e da aprovação concedidas ao aplicativo. Qualquer publicação futura exigirá aprovação humana explícita, salvo se houver um fluxo autorizado definido.

## Objetivos

- Analisar informações profissionais do perfil e sugerir melhorias.
- Gerar ideias e rascunhos de publicações para revisão humana.
- Ajudar a planejar um calendário de publicações e resumir métricas disponíveis.
- Identificar assuntos e tendências profissionais relevantes usando fontes permitidas.
- Executar tarefas agendadas ou iniciadas manualmente na nuvem quando o projeto estiver pronto.
- Manter credenciais fora do controle de versão e usar GitHub Secrets nos fluxos na nuvem.

Esses itens são objetivos do projeto, não funcionalidades já disponíveis.

## Arquitetura inicial

A primeira versão manterá um núcleo Python pequeno e adicionará módulos apenas quando uma funcionalidade precisar deles:

| Caminho | Responsabilidade |
| --- | --- |
| `app/main.py` | Criação da aplicação FastAPI e ciclo de vida do banco. |
| `config/settings.py` | Configurações sem dependências externas, lidas das variáveis de ambiente, com validação do nível de log e representação que não expõe segredos. |
| `requirements.txt` | Dependências de execução, incluindo FastAPI, SQLAlchemy, Alembic, psycopg e ferramentas de autenticação. |
| `requirements-dev.txt` | Dependências de desenvolvimento, incluindo Pytest. |
| `tests/test_settings.py` | Testes unitários para valores padrão, normalização, validação e proteção de segredos. |
| `app/models/search_criteria.py` | Modelo validado e independente de persistência para os critérios de busca. |
| `app/services/search_criteria_service.py` | Atualização, substituição e limpeza dos critérios em memória. |
| `tests/test_search_criteria.py` | Testes do modelo e do serviço de critérios de busca. |
| `app/models/professional_profile.py` | Modelos de domínio independentes para dados do perfil profissional. |
| `app/services/professional_profile_service.py` | Gerenciamento em memória do perfil profissional. |
| `app/models/job_vacancy.py` e `app/services/compatibility_service.py` | Modelo de vaga e avaliação de compatibilidade com o perfil. |
| `app/db/` | Base declarativa, engine, sessões e modelos ORM separados do domínio. |
| `app/repositories/` | Persistência e conversão dos critérios, perfil e vagas. |
| `migrations/` e `alembic.ini` | Revisões versionadas do esquema com Alembic. |
| `tests/test_database_persistence.py` | Testes dos repositórios com SQLite em memória. |
| `tests/test_database_migrations.py` | Verificação de upgrade e downgrade da migration inicial. |
| `app/security/` e `app/services/authentication_service.py` | Hash de senhas, validação de JWT e regras de sessão. |
| `app/api/` e `app/schemas/auth.py` | Rotas de autenticação, dependências e schemas HTTP. |
| `migrations/versions/` | Evolução aditiva de usuários e criação de sessões/tokens. |
| `.env.example` | Nomes das configurações locais previstas, sem credenciais. |

Os modelos ORM ficam separados das dataclasses de domínio. Critérios e perfil são associados a um `user_id`; as vagas formam um catálogo compartilhado. A tabela mínima de usuários ainda não contém credenciais de autenticação.

## Configuração local

Use Python 3.11 ou mais recente. No PowerShell, ative o ambiente virtual `.venv` do projeto e instale as dependências de desenvolvimento (que também incluem as dependências de execução):

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest
```

O módulo de configurações lê variáveis do ambiente do processo. Use `.env.example` como referência local e disponibilize os valores ao processo pelo ambiente de desenvolvimento; a aplicação não interpreta arquivos `.env` diretamente.

## Banco de dados e migrations

PostgreSQL é o banco principal. Defina `DATABASE_URL` no ambiente local com uma URL no formato `postgresql+psycopg://...`; não grave credenciais em arquivos versionados. O repositório não cria o banco PostgreSQL nem inicia serviços automaticamente. Depois de preparar um banco e configurar a URL, aplique o esquema com:

```powershell
python -m alembic upgrade head
```

Os testes de persistência usam SQLite em memória e não exigem servidor PostgreSQL. As chaves estrangeiras do SQLite são habilitadas pelo engine de testes.

## Autenticação e sessões

A API oferece cadastro, login, renovação, logout e consulta do usuário autenticado em `/auth`. Senhas são armazenadas com Argon2id; access tokens JWT e refresh tokens não são retornados no corpo JSON. O access token e o refresh token são enviados em cookies `HttpOnly`; o cookie CSRF é acompanhado pelo cabeçalho `X-CSRF-Token` nas operações protegidas. Em produção, cookies `Secure` são obrigatórios. O refresh token é rotacionado e apenas seu hash é persistido.

Defina `JWT_SECRET_KEY` no ambiente do processo. Para desenvolvimento local, gere uma chave com:

```powershell
$env:JWT_SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Em HTTP local, mantenha a chave apenas no ambiente do terminal e use `AUTH_COOKIE_SECURE=false`; em produção mantenha `AUTH_COOKIE_SECURE=true`. `AUTH_COOKIE_SAMESITE` aceita `lax`, `strict` ou `none`; o último exige cookies `Secure`. `JWT_ISSUER`, `JWT_AUDIENCE`, `ACCESS_TOKEN_TTL_MINUTES` e `REFRESH_TOKEN_TTL_DAYS` também podem ser ajustados pelo ambiente. O arquivo `.env.example` documenta os nomes, mas a aplicação não lê arquivos `.env` diretamente.

Para iniciar a API localmente, depois de preparar o banco e aplicar as migrations:

```powershell
python -m uvicorn app.main:app --reload
```

Linhas de usuário legadas sem e-mail e senha permanecem preservadas pela migration, mas não podem autenticar até uma futura vinculação explícita. Recuperação e verificação de e-mail não fazem parte desta etapa.

## Dados pessoais por usuário

Os endpoints `/me/search-criteria` e `/me/professional-profile` consultam e alteram somente os dados associados ao usuário autenticado. Ambos aceitam `GET`, `PUT`, `PATCH` e `DELETE`; operações de alteração exigem o cabeçalho CSRF. `PUT` substitui o recurso e cria quando ainda não existe; `PATCH` altera somente os campos enviados. Corpos de entrada não aceitam `user_id` nem IDs de proprietário, e as rotas não recebem IDs de outros usuários. O identificador usado pelos repositórios vem exclusivamente do principal extraído do token.

Os critérios e perfis continuam associados por `user_id`, com as chaves estrangeiras e restrições de unicidade existentes. A API não altera o catálogo compartilhado de vagas. Novos dados pessoais devem seguir o mesmo padrão: obter o proprietário da identidade autenticada e delimitar toda operação ao seu identificador.

## Configuração e segurança

- Nunca versione `.env`, tokens de acesso, segredos de cliente ou chaves de API.
- `.gitignore` exclui `.env` e ambientes virtuais, permitindo que `.env.example` seja versionado.
- Use GitHub Secrets para credenciais em futuros fluxos do GitHub Actions; nunca coloque valores secretos nos arquivos de fluxo.
- Solicite somente as permissões necessárias da API oficial do LinkedIn. O acesso à API e a publicação podem exigir aprovação do LinkedIn.
- Mantenha uma etapa de aprovação humana antes de publicar ou executar outras ações externas.

## Desenvolvimento

Execute os testes unitários com `python -m pytest`. Pytest é uma dependência exclusiva de desenvolvimento, declarada em `requirements-dev.txt`; as dependências de execução permanecem separadas em `requirements.txt`.

Use Conventional Commits nas próximas alterações, por exemplo, `feat: adicionar gerador de rascunhos` ou `docs: documentar configuração local`. Não faça commit ou push sem autorização explícita.

`APP_ENV` aceita `development`, `test`, `staging` ou `production`; valores desconhecidos impedem a inicialização. Defina explicitamente `APP_ENV=production` na implantação. Em produção, configure também `AUTH_COOKIE_SECURE=true`, `JWT_SECRET_KEY` e `DATABASE_URL`; a aplicação recusa iniciar sem esses requisitos.

Cadastro e login têm limites independentes por endereço IP e por conta: login permite até 30 tentativas por IP e 10 por e-mail a cada 15 minutos; cadastro permite até 20 por IP e 5 por e-mail a cada hora. A resposta `429` é genérica e inclui `Retry-After`. O IP vem do peer da conexão ASGI; cabeçalhos encaminhados fornecidos pelo cliente não são usados diretamente. Se houver proxy reverso, configure no servidor ASGI somente os endereços de proxy confiáveis.

O armazenamento atual dos limites é em memória local ao processo e serve para desenvolvimento ou execução de instância única. Ele não compartilha contadores entre múltiplos processos ou instâncias e, portanto, não oferece proteção suficiente em produção distribuída. A interface `RateLimitStore` permite substituir esse armazenamento por uma implementação compartilhada, como Redis, em uma etapa futura; nenhum serviço externo é necessário agora.

## Execução na nuvem

GitHub Actions é a primeira opção a avaliar para verificações leves e tarefas iniciadas manualmente ou de forma periódica. Ele pode executar sem que o computador de desenvolvimento esteja ligado, mas os agendamentos são de melhor esforço: o GitHub informa que podem ocorrer atrasos e execuções descartadas em períodos de alta demanda. As cotas e cobranças dependem da visibilidade do repositório e do plano da conta; confira os limites atuais antes de habilitar tarefas recorrentes. GitHub Actions não é um agendador em tempo real.

- [Eventos de fluxos agendados](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [Faturamento do GitHub Actions](https://docs.github.com/en/billing/concepts/product-billing/github-actions)

## Próximas etapas

1. Confirmar a estrutura inicial do projeto e aprovar a primeira funcionalidade.
2. Implementar uma base pequena e testável, com configurações e tratamento de erros.
3. Adicionar um fluxo de criação de rascunhos com revisão humana e provedor documentado com clareza.
4. Avaliar o acesso à API oficial do LinkedIn e implementar somente escopos aprovados.
5. Adicionar relatórios e agendamentos com base nos dados e recursos realmente disponíveis.
6. Adicionar GitHub Actions depois de definir os segredos, as permissões e o comportamento dos processos necessários.

## Licença

Ainda não foi escolhida uma licença. Adicione uma antes de distribuir o projeto ou aceitar contribuições.
