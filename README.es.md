# AI Council

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Leer en:** [English](README.md) · [Português (BR)](README.pt-BR.md) · Español · [中文](README.zh-CN.md)

**Pon a Claude, ChatGPT, Gemini y DeepSeek en la misma sala — y míralas debatir tu problema en tiempo real.**

AI Council es una **sala de control multiagente** self-hosted: varios modelos de frontera argumentan, refinan ideas, llaman herramientas y entregan una síntesis — mientras observas terminales en vivo, rastreas costos por IA y entras en la conversación cuando quieras. Sin cuentas, sin dependencia de la nube. Tu máquina, tus claves, tus datos.

> **Por qué los equipos lo usan:** obtén perspectivas diversas sin copiar y pegar entre pestañas; ve surgir los desacuerdos antes de decidir; mantén un registro de auditoría completo en PostgreSQL.

---

## Cómo funciona

```mermaid
flowchart TB
    subgraph YOU["👤 Tú"]
        A[Definir meta, rondas y presupuesto]
        B[Elegir IAs, modelos y personas]
        C[Observar en vivo — o unirte al chat]
    end

    subgraph COUNCIL["🧠 AI Council"]
        D[Orquestador ejecuta rondas de debate]
        E1[Claude]
        E2[ChatGPT]
        E3[Gemini]
        E4[DeepSeek]
        D --> E1 & E2 & E3 & E4
    end

    subgraph TOOLS["🔧 Herramientas opcionales"]
        T1[Búsqueda y lectura web]
        T2[Actores Apify]
        T3[Servidores MCP]
    end

    subgraph OUTPUT["📊 Resultados"]
        F[Marcador en vivo — tokens y costo]
        G[Síntesis final]
        H[(PostgreSQL — historial completo)]
    end

    A --> D
    B --> D
    E1 & E2 & E3 & E4 <--> T1 & T2 & T3
    D --> F
    D --> G
    D --> H
    C -.->|Pausar / Reanudar / Mensaje humano| D
    F & G --> C
```

**En términos simples:**

1. **Tú defines la misión** — meta, número de rondas, presupuesto de tokens, modo secuencial o paralelo, qué IAs participan y personas opcionales.
2. **El consejo debate** — cada IA habla por turnos (o todas a la vez en modo paralelo), puede usar herramientas web/Apify/MCP y construye sobre lo que dijeron las demás.
3. **Tú mantienes el control** — pausa, reanuda, detén o envía un mensaje como humano; tu aporte entra en el siguiente turno de IA.
4. **Obtienes respuestas y rendición de cuentas** — síntesis final, marcador de costo por IA, terminales de agentes en vivo y todo guardado en PostgreSQL.

---

## Ejecutar (recomendado — CLIs locales)

La app corre **en tu máquina** (usa CLIs instaladas) y solo Postgres corre en Docker:

```bash
cp .env.example .env        # opcional: herramientas y respaldo de API key
npm run dev
```

Abre **http://localhost:8000** (o **8002** si la 8000 está ocupada — el script avisa en la terminal). Configura y prueba las CLIs en **/settings**.

`npm run dev` inicia Postgres automáticamente (`localhost:5433`) y define `DATABASE_URL` — no necesitas editar `.env` para la base de datos.

> Sin autenticación por diseño — **no expongas en internet**. Ejecuta en localhost
> o detrás de VPN/proxy con autenticación.

### Otros comandos

| Comando | Qué hace |
|---------|----------|
| `npm run dev` | App local + Postgres en Docker (predeterminado) |
| `npm run docker:db` | Solo Postgres (primer plano) |
| `npm run docker:up` | Stack completo en Docker (API keys; CLIs del host **no** funcionan) |

## Configurar CLIs

1. Instala las CLIs en tu terminal (`claude`, `codex`, `gemini`, `deepseek-tui`).
2. Autentica cada una (`claude auth login`, `codex login`, etc.).
3. Abre **/settings**, haz clic en **Test** y confirma la respuesta.

O usa API keys en `.env` como respaldo (desmarca "Prefer local CLIs" en /settings).

## Funciones en detalle

### Modos
- **Secuencial** ("Wait for each other" marcado): cada IA ve lo que dijo la
  anterior en la misma ronda.
- **Paralelo** (desmarcado): todas hablan a la vez, cada una viendo el estado
  al inicio de la ronda. Más rápido, menos "conversación".

### Por IA, tú controlas
- Modelo (lista editable + opción personalizada).
- Si está **activa** en la conversación.
- Si **puede preguntar / intercambiar ideas** (cambia el comportamiento del prompt).
- Persona opcional.

### Herramientas
- **Web**: `web_search` (usa Tavily si `TAVILY_API_KEY` está definida, si no DuckDuckGo)
  y `web_fetch` (lee texto de una URL).
- **Apify**: `apify_run` ejecuta un Actor y devuelve ítems del dataset (requiere
  `APIFY_TOKEN`).
- **MCP**: servidores configurados en `mcp_servers.json` se convierten en herramientas
  disponibles para las IAs.

### Marcador (por IA, en tiempo real)
Tokens de entrada/salida, **costo estimado** (USD), **turnos**
completados y **herramientas** (llamadas). Más una tarjeta de total.

## Arquitectura

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

La comunicación en tiempo real usa WebSocket (`/ws/{id}`). Eventos del servidor:
`snapshot`, `status`, `round`, `turn_start`, `message`, `agent_step`,
`scoreboard`, `log`, `error`.

## Configurar MCP

Edita `mcp_servers.json`:

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

Al crear una conversación, marca **MCP** en herramientas. (Node/npx requerido en PATH.)

## Ejecutar manualmente (sin npm run dev)

Requiere Postgres accesible. Con el DB Docker ya en ejecución (`npm run docker:db`):

```bash
pip install -r requirements.txt
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/aicouncil uvicorn app.main:app --reload
```

## Notas honestas

- **Precios y nombres de modelos** en `catalog.py` son puntos de partida y cambian con frecuencia —
  confirma y edita. "Costo" es una **estimación**.
- **MCP** es la parte más dependiente del entorno. Está implementado y aislado
  (los fallos no tumban la app), pero valida con los servidores que uses.
- **Stop** interrumpe en los límites de turno; un turno ya en curso
  termina primero (las herramientas tienen timeouts).
- **Modo CLI** (vía `npm run dev`) no usa herramientas web/Apify/MCP para las IAs —
  solo texto. Para herramientas, usa API keys o `npm run docker:up`.

## Licencia

Copyright © 2026 Sólon Abuquerque. Distribuido bajo la [Licencia MIT](LICENSE).

---

## Palabras clave

Términos de búsqueda que la gente usa para encontrar proyectos como este:

**English:** multi-agent AI, AI debate, AI council, LLM orchestration, multi-model chat, Claude ChatGPT Gemini together, AI collaboration tool, self-hosted AI platform, real-time AI dashboard, AI cost tracker, token usage scoreboard, human-in-the-loop AI, AI synthesis, parallel AI agents, sequential AI debate, MCP tools for LLMs, FastAPI WebSocket AI, PostgreSQL AI conversations, local AI CLI, OpenAI Anthropic Google DeepSeek

**Português:** debate entre IAs, conselho de inteligência artificial, múltiplos agentes IA, orquestração de LLM, Claude ChatGPT Gemini juntos, ferramenta de colaboração IA, plataforma IA self-hosted, painel IA em tempo real, controle de custo IA, scoreboard de tokens, humano no loop, síntese com IA, agentes IA paralelos, debate sequencial IA, ferramentas MCP para LLM, conversas IA PostgreSQL, CLI local IA

**Español:** debate entre IAs, consejo de inteligencia artificial, múltiples agentes IA, orquestación de LLM, Claude ChatGPT Gemini juntos, herramienta de colaboración IA, plataforma IA self-hosted, panel IA en tiempo real, control de costos IA, marcador de tokens, humano en el bucle, síntesis con IA, agentes IA en paralelo, debate secuencial IA, herramientas MCP para LLM, conversaciones IA PostgreSQL, CLI local IA
