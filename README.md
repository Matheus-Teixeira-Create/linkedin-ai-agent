# Agente de IA para LinkedIn

Assistente de inteligência artificial para planejar e aprimorar uma presença profissional no LinkedIn. O projeto está sendo desenvolvido de forma incremental, com revisão humana para ações externas e uso exclusivo de integrações oficiais e autorizadas.

## Estado do projeto

Este repositório contém atualmente configurações lidas do ambiente e os respectivos testes unitários. Nenhum provedor de IA, API do LinkedIn, fluxo na nuvem ou recurso de publicação está implementado ou conectado. O projeto não coleta dados do LinkedIn por scraping nem automatiza curtidas, comentários, conexões ou mensagens.

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
| `app/main.py` | Ponto de entrada da aplicação; ainda não implementado. |
| `config/settings.py` | Configurações sem dependências externas, lidas das variáveis de ambiente, com validação do nível de log e representação que não expõe segredos. |
| `requirements.txt` | Dependências de execução. Ainda não há dependências externas de execução. |
| `requirements-dev.txt` | Dependências de desenvolvimento, incluindo Pytest. |
| `tests/test_settings.py` | Testes unitários para valores padrão, normalização, validação e proteção de segredos. |
| `app/models/search_criteria.py` | Modelo validado e independente de persistência para os critérios de busca. |
| `app/services/search_criteria_service.py` | Atualização, substituição e limpeza dos critérios em memória. |
| `tests/test_search_criteria.py` | Testes do modelo e do serviço de critérios de busca. |
| `.env.example` | Nomes das configurações locais previstas, sem credenciais. |

À medida que as funcionalidades forem aprovadas, poderão ser adicionados serviços, modelos, testes, documentação e fluxos do GitHub Actions quando houver necessidade real. O desenho inicial não exige FastAPI nem banco de dados; essas escolhas poderão ser reavaliadas quando houver um caso de uso concreto.

## Configuração local

Use Python 3.11 ou mais recente. No PowerShell, ative o ambiente virtual `venv` existente e instale as dependências de desenvolvimento:

```powershell
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest
```

O módulo de configurações lê variáveis do ambiente do processo. Use `.env.example` como referência local e disponibilize os valores ao processo pelo ambiente de desenvolvimento; a aplicação não interpreta arquivos `.env` diretamente.

## Configuração e segurança

- Nunca versione `.env`, tokens de acesso, segredos de cliente ou chaves de API.
- `.gitignore` exclui `.env` e ambientes virtuais, permitindo que `.env.example` seja versionado.
- Use GitHub Secrets para credenciais em futuros fluxos do GitHub Actions; nunca coloque valores secretos nos arquivos de fluxo.
- Solicite somente as permissões necessárias da API oficial do LinkedIn. O acesso à API e a publicação podem exigir aprovação do LinkedIn.
- Mantenha uma etapa de aprovação humana antes de publicar ou executar outras ações externas.

## Desenvolvimento

Execute os testes unitários com `python -m pytest`. Pytest é uma dependência exclusiva de desenvolvimento, declarada em `requirements-dev.txt`; as dependências de execução permanecem separadas em `requirements.txt`.

Use Conventional Commits nas próximas alterações, por exemplo, `feat: adicionar gerador de rascunhos` ou `docs: documentar configuração local`. Não faça commit ou push sem autorização explícita.

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
