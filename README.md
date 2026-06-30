# AI Council — v2

Platform where multiple AIs (Claude, ChatGPT, Gemini, DeepSeek) **debate in real time**
to solve a problem, with tools (web, Apify, MCP), per-AI cost scoreboard, live terminals
showing each one at work, and human participation in chat. Everything persisted in PostgreSQL. No login.

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

## How it works

1. **+ New conversation**: set goal, number of rounds, token budget,
   mode (sequential or parallel), tools, and which AIs participate (with model
   and persona for each).
2. **Start**: AIs speak in rounds. At the end, one produces a **synthesis**.
3. You can **Pause/Resume/Stop** and **join the chat as a human** at any
   time — your message enters the conversation the next time an AI speaks.

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
