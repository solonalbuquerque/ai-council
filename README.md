# AI Council

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Put Claude, ChatGPT, Gemini, and DeepSeek in the same room — and watch them debate your problem in real time.**

AI Council is a self-hosted **multi-agent control room**: several frontier models argue, refine ideas, call tools, and deliver a synthesis — while you observe live terminals, track costs per AI, and jump into the conversation whenever you want. No accounts, no cloud lock-in. Your machine, your keys, your data.

> **Why teams use it:** get diverse perspectives without copy-pasting between tabs; see disagreements surface before you commit to a decision; keep a full audit trail in PostgreSQL.

---

## How it works

```mermaid
flowchart TB
    subgraph YOU["👤 You"]
        A[Define goal, rounds & budget]
        B[Choose AIs, models & personas]
        C[Watch live — or join the chat]
    end

    subgraph COUNCIL["🧠 AI Council"]
        D[Orchestrator runs debate rounds]
        E1[Claude]
        E2[ChatGPT]
        E3[Gemini]
        E4[DeepSeek]
        D --> E1 & E2 & E3 & E4
    end

    subgraph TOOLS["🔧 Tools optional"]
        T1[Web search & fetch]
        T2[Apify actors]
        T3[MCP servers]
    end

    subgraph OUTPUT["📊 Results"]
        F[Live scoreboard — tokens & cost]
        G[Final synthesis]
        H[(PostgreSQL — full history)]
    end

    A --> D
    B --> D
    E1 & E2 & E3 & E4 <--> T1 & T2 & T3
    D --> F
    D --> G
    D --> H
    C -.->|Pause / Resume / Human message| D
    F & G --> C
```

**In plain terms:**

1. **You set the mission** — goal, number of rounds, token budget, sequential or parallel mode, which AIs participate, and optional personas.
2. **The council debates** — each AI speaks in turns (or all at once in parallel mode), can use web/Apify/MCP tools, and builds on what others said.
3. **You stay in control** — pause, resume, stop, or send a message as a human; your input enters the next AI turn.
4. **You get answers and accountability** — a final synthesis, per-AI cost scoreboard, live agent terminals, and everything saved to PostgreSQL.

---

## Run (recommended — local CLIs)

The app runs **on your machine** (uses installed CLIs) and only Postgres runs in Docker:

```bash
cp .env.example .env        # optional: tools and API key fallback
npm run dev
```

Open **http://localhost:8000** (or **8002** if 8000 is busy — the script warns in the terminal). Configure and test CLIs at **/settings**.

`npm run dev` starts Postgres automatically (`localhost:5433`) and sets `DATABASE_URL` — you do not need to edit `.env` for the database.

> No authentication by design — **do not expose on the internet**. Run on localhost
> or behind a VPN/proxy with authentication.

### Other commands

| Command | What it does |
|---------|--------------|
| `npm run dev` | Local app + Postgres in Docker (default) |
| `npm run docker:db` | Postgres only (foreground) |
| `npm run docker:up` | Full stack in Docker (API keys; host CLIs **do not** work) |

## Configure CLIs

1. Install CLIs in your terminal (`claude`, `codex`, `gemini`, `deepseek-tui`).
2. Authenticate each one (`claude auth login`, `codex login`, etc.).
3. Open **/settings**, click **Test** and confirm the response.

Or use API keys in `.env` as fallback (uncheck "Prefer local CLIs" in /settings).

## Features in detail

### Modes
- **Sequential** ("Wait for each other" checked): each AI sees what the
  previous one said in the same round.
- **Parallel** (unchecked): all speak at once, each seeing the state
  at the start of the round. Faster, less of a "conversation".

### Per AI, you control
- Model (editable list + custom option).
- Whether it is **active** in the conversation.
- Whether it **can ask / exchange ideas** (changes prompt behavior).
- Optional persona.

### Tools
- **Web**: `web_search` (uses Tavily if `TAVILY_API_KEY` is set, otherwise DuckDuckGo)
  and `web_fetch` (reads text from a URL).
- **Apify**: `apify_run` runs an Actor and returns dataset items (requires
  `APIFY_TOKEN`).
- **MCP**: servers configured in `mcp_servers.json` become tools
  available to the AIs.

### Scoreboard (per AI, real time)
Input/output tokens, **estimated cost** (USD), **turns**
completed, and **tools** (calls). Plus a total card.

## Architecture

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

Real-time communication uses WebSocket (`/ws/{id}`). Server events:
`snapshot`, `status`, `round`, `turn_start`, `message`, `agent_step`,
`scoreboard`, `log`, `error`.

## Configure MCP

Edit `mcp_servers.json`:

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

When creating a conversation, check **MCP** under tools. (Node/npx required in PATH.)

## Run manually (without npm run dev)

Requires an accessible Postgres. With Docker DB already running (`npm run docker:db`):

```bash
pip install -r requirements.txt
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/aicouncil uvicorn app.main:app --reload
```

## Honest notes

- **Prices and model names** in `catalog.py` are starting points and change often —
  confirm and edit. "Cost" is an **estimate**.
- **MCP** is the most environment-dependent part. It is implemented and isolated
  (failures do not crash the app), but validate with the servers you use.
- **Stop** interrupts at turn boundaries; a turn already in progress
  finishes first (tools have timeouts).
- **CLI mode** (via `npm run dev`) does not use web/Apify/MCP tools for AIs —
  text only. For tools, use API keys or `npm run docker:up`.

## License

Copyright © 2026 Sólon Abuquerque. Released under the [MIT License](LICENSE).

---

## Keywords

Search terms people use to find projects like this:

**English:** multi-agent AI, AI debate, AI council, LLM orchestration, multi-model chat, Claude ChatGPT Gemini together, AI collaboration tool, self-hosted AI platform, real-time AI dashboard, AI cost tracker, token usage scoreboard, human-in-the-loop AI, AI synthesis, parallel AI agents, sequential AI debate, MCP tools for LLMs, FastAPI WebSocket AI, PostgreSQL AI conversations, local AI CLI, OpenAI Anthropic Google DeepSeek

**Português:** debate entre IAs, conselho de inteligência artificial, múltiplos agentes IA, orquestração de LLM, Claude ChatGPT Gemini juntos, ferramenta de colaboração IA, plataforma IA self-hosted, painel IA em tempo real, controle de custo IA, scoreboard de tokens, humano no loop, síntese com IA, agentes IA paralelos, debate sequencial IA, ferramentas MCP para LLM, conversas IA PostgreSQL, CLI local IA

**Español:** debate entre IAs, consejo de inteligencia artificial, múltiples agentes IA, orquestación de LLM, Claude ChatGPT Gemini juntos, herramienta de colaboración IA, plataforma IA self-hosted, panel IA en tiempo real, control de costos IA, marcador de tokens, humano en el bucle, síntesis con IA, agentes IA en paralelo, debate secuencial IA, herramientas MCP para LLM, conversaciones IA PostgreSQL, CLI local IA
