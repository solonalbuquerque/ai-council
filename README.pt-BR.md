# AI Council

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Leia em:** [English](README.md) · Português (BR) · [Español](README.es.md) · [中文](README.zh-CN.md)

**Coloque Claude, ChatGPT, Gemini e DeepSeek na mesma sala — e veja elas debaterem seu problema em tempo real.**

O AI Council é uma **sala de controle multiagente** self-hosted: vários modelos de ponta argumentam, refinam ideias, chamam ferramentas e entregam uma síntese — enquanto você observa terminais ao vivo, acompanha custos por IA e entra na conversa quando quiser. Sem contas, sem lock-in na nuvem. Sua máquina, suas chaves, seus dados.

> **Por que equipes usam:** obtenha perspectivas diversas sem copiar e colar entre abas; veja divergências surgirem antes de decidir; mantenha trilha de auditoria completa no PostgreSQL.

---

## Como funciona

```mermaid
flowchart TB
    subgraph YOU["👤 Você"]
        A[Definir meta, rodadas e orçamento]
        B[Escolher IAs, modelos e personas]
        C[Acompanhar ao vivo — ou entrar no chat]
    end

    subgraph COUNCIL["🧠 AI Council"]
        D[Orquestrador executa rodadas de debate]
        E1[Claude]
        E2[ChatGPT]
        E3[Gemini]
        E4[DeepSeek]
        D --> E1 & E2 & E3 & E4
    end

    subgraph TOOLS["🔧 Ferramentas opcionais"]
        T1[Busca e leitura web]
        T2[Atores Apify]
        T3[Servidores MCP]
    end

    subgraph OUTPUT["📊 Resultados"]
        F[Placar ao vivo — tokens e custo]
        G[Síntese final]
        H[(PostgreSQL — histórico completo)]
    end

    A --> D
    B --> D
    E1 & E2 & E3 & E4 <--> T1 & T2 & T3
    D --> F
    D --> G
    D --> H
    C -.->|Pausar / Retomar / Mensagem humana| D
    F & G --> C
```

**Em termos simples:**

1. **Você define a missão** — meta, número de rodadas, orçamento de tokens, modo sequencial ou paralelo, quais IAs participam e personas opcionais.
2. **O conselho debate** — cada IA fala em turnos (ou todas de uma vez no modo paralelo), pode usar ferramentas web/Apify/MCP e constrói sobre o que as outras disseram.
3. **Você mantém o controle** — pause, retome, pare ou envie uma mensagem como humano; sua entrada entra no próximo turno de IA.
4. **Você obtém respostas e prestação de contas** — síntese final, placar de custo por IA, terminais dos agentes ao vivo e tudo salvo no PostgreSQL.

---

## Executar (recomendado — CLIs locais)

O app roda **na sua máquina** (usa CLIs instaladas) e apenas o Postgres roda no Docker:

```bash
cp .env.example .env        # opcional: ferramentas e fallback de API key
npm run dev
```

Abra **http://localhost:8000** (ou **8002** se a 8000 estiver ocupada — o script avisa no terminal). Configure e teste as CLIs em **/settings**.

O `npm run dev` inicia o Postgres automaticamente (`localhost:5433`) e define `DATABASE_URL` — você não precisa editar o `.env` para o banco.

> Sem autenticação por design — **não exponha na internet**. Rode em localhost
> ou atrás de VPN/proxy com autenticação.

### Outros comandos

| Comando | O que faz |
|---------|-----------|
| `npm run dev` | App local + Postgres no Docker (padrão) |
| `npm run docker:db` | Apenas Postgres (primeiro plano) |
| `npm run docker:up` | Stack completa no Docker (API keys; CLIs do host **não** funcionam) |

## Configurar CLIs

1. Instale as CLIs no terminal (`claude`, `codex`, `gemini`, `deepseek-tui`).
2. Autentique cada uma (`claude auth login`, `codex login`, etc.).
3. Abra **/settings**, clique em **Test** e confirme a resposta.

Ou use API keys no `.env` como fallback (desmarque "Prefer local CLIs" em /settings).

## Recursos em detalhe

### Modos
- **Sequencial** ("Wait for each other" marcado): cada IA vê o que a
  anterior disse na mesma rodada.
- **Paralelo** (desmarcado): todas falam ao mesmo tempo, cada uma vendo o estado
  no início da rodada. Mais rápido, menos "conversa".

### Por IA, você controla
- Modelo (lista editável + opção customizada).
- Se está **ativa** na conversa.
- Se **pode perguntar / trocar ideias** (altera o comportamento do prompt).
- Persona opcional.

### Ferramentas
- **Web**: `web_search` (usa Tavily se `TAVILY_API_KEY` estiver definida, senão DuckDuckGo)
  e `web_fetch` (lê texto de uma URL).
- **Apify**: `apify_run` executa um Actor e retorna itens do dataset (requer
  `APIFY_TOKEN`).
- **MCP**: servidores configurados em `mcp_servers.json` viram ferramentas
  disponíveis para as IAs.

### Placar (por IA, em tempo real)
Tokens de entrada/saída, **custo estimado** (USD), **turnos**
concluídos e **ferramentas** (chamadas). Mais um card de total.

## Arquitetura

```
app/
  main.py          FastAPI: REST + WebSocket + serve frontend
  db.py            async engine (SQLAlchemy 2.0 + asyncpg)
  models.py        Conversation, Participant, Message, UsageEvent
  store.py         database access + scoreboard aggregation
  catalog.py       models per provider + price table (EDIT)
  providers.py     adapters with tool loop (OpenAI-compat + Anthropic)
  orchestrator.py  engine: rounds, sequential/parallel, human, budget, synthesis
  tools/           web, apify, mcp_bridge
web/               index.html, styles.css, app.js (real-time control room)
```

A comunicação em tempo real usa WebSocket (`/ws/{id}`). Eventos do servidor:
`snapshot`, `status`, `round`, `turn_start`, `message`, `agent_step`,
`scoreboard`, `log`, `error`.

## Configurar MCP

Edite `mcp_servers.json`:

```json
{
  "servers": [
    {
      "name": "filesystem",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"],
      "enabled": true
    }
  ]
}
```

Ao criar uma conversa, marque **MCP** em ferramentas. (Node/npx necessário no PATH.)

## Executar manualmente (sem npm run dev)

Requer Postgres acessível. Com o DB Docker já rodando (`npm run docker:db`):

```bash
pip install -r requirements.txt
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/aicouncil uvicorn app.main:app --reload
```

## Notas honestas

- **Preços e nomes de modelos** em `catalog.py` são pontos de partida e mudam com frequência —
  confirme e edite. "Custo" é uma **estimativa**.
- **MCP** é a parte mais dependente do ambiente. Está implementado e isolado
  (falhas não derrubam o app), mas valide com os servidores que você usa.
- **Stop** interrompe nos limites de turno; um turno já em andamento
  termina primeiro (ferramentas têm timeouts).
- **Modo CLI** (via `npm run dev`) não usa ferramentas web/Apify/MCP para as IAs —
  apenas texto. Para ferramentas, use API keys ou `npm run docker:up`.

## Licença

Copyright © 2026 Sólon Abuquerque. Distribuído sob a [Licença MIT](LICENSE).

---

## Palavras-chave

Termos de busca que as pessoas usam para encontrar projetos como este:

**English:** multi-agent AI, AI debate, AI council, LLM orchestration, multi-model chat, Claude ChatGPT Gemini together, AI collaboration tool, self-hosted AI platform, real-time AI dashboard, AI cost tracker, token usage scoreboard, human-in-the-loop AI, AI synthesis, parallel AI agents, sequential AI debate, MCP tools for LLMs, FastAPI WebSocket AI, PostgreSQL AI conversations, local AI CLI, OpenAI Anthropic Google DeepSeek

**Português:** debate entre IAs, conselho de inteligência artificial, múltiplos agentes IA, orquestração de LLM, Claude ChatGPT Gemini juntos, ferramenta de colaboração IA, plataforma IA self-hosted, painel IA em tempo real, controle de custo IA, scoreboard de tokens, humano no loop, síntese com IA, agentes IA paralelos, debate sequencial IA, ferramentas MCP para LLM, conversas IA PostgreSQL, CLI local IA

**Español:** debate entre IAs, consejo de inteligencia artificial, múltiples agentes IA, orquestación de LLM, Claude ChatGPT Gemini juntos, herramienta de colaboración IA, plataforma IA self-hosted, panel IA en tiempo real, control de costos IA, marcador de tokens, humano en el bucle, síntesis con IA, agentes IA en paralelo, debate secuencial IA, herramientas MCP para LLM, conversaciones IA PostgreSQL, CLI local IA
