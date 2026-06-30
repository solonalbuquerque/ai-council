# AI Council

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**阅读语言：** [English](README.md) · [Português (BR)](README.pt-BR.md) · [Español](README.es.md) · 中文

**让 Claude、ChatGPT、Gemini 和 DeepSeek 坐在同一间「会议室」——实时观看它们辩论你的问题。**

AI Council 是一个可自托管的**多智能体控制室**：多个前沿模型争论观点、打磨想法、调用工具并产出综合结论——同时你可以查看实时终端、追踪每个 AI 的成本，并随时加入对话。无需账号，无云厂商锁定。你的机器、你的密钥、你的数据。

> **团队为何使用：** 无需在多个标签页之间复制粘贴即可获得多元视角；在做出决策前看到分歧浮现；在 PostgreSQL 中保留完整审计记录。

---

## 工作原理

```mermaid
flowchart TB
    subgraph YOU["👤 你"]
        A[设定目标、轮次与预算]
        B[选择 AI、模型与人设]
        C[实时观看 — 或加入聊天]
    end

    subgraph COUNCIL["🧠 AI Council"]
        D[编排器运行辩论轮次]
        E1[Claude]
        E2[ChatGPT]
        E3[Gemini]
        E4[DeepSeek]
        D --> E1 & E2 & E3 & E4
    end

    subgraph TOOLS["🔧 可选工具"]
        T1[网络搜索与抓取]
        T2[Apify Actor]
        T3[MCP 服务器]
    end

    subgraph OUTPUT["📊 结果"]
        F[实时记分板 — Token 与成本]
        G[最终综合结论]
        H[(PostgreSQL — 完整历史)]
    end

    A --> D
    B --> D
    E1 & E2 & E3 & E4 <--> T1 & T2 & T3
    D --> F
    D --> G
    D --> H
    C -.->|暂停 / 恢复 / 人类消息| D
    F & G --> C
```

**简单来说：**

1. **你设定任务** — 目标、轮次数、Token 预算、顺序或并行模式、参与的 AI 及可选人设。
2. **理事会辩论** — 每个 AI 轮流发言（或并行模式下同时发言），可使用 Web/Apify/MCP 工具，并基于他人观点继续推进。
3. **你保持掌控** — 暂停、恢复、停止，或以人类身份发送消息；你的输入将在下一轮 AI 发言时纳入。
4. **你获得答案与可追溯性** — 最终综合结论、按 AI 统计的成本记分板、实时代理终端，以及全部保存至 PostgreSQL。

---

## 运行（推荐 — 本地 CLI）

应用在**你的机器上**运行（使用已安装的 CLI），仅 Postgres 在 Docker 中运行：

```bash
cp .env.example .env        # 可选：工具与 API 密钥备用
npm run dev
```

打开 **http://localhost:8000**（若 8000 被占用则为 **8002** — 脚本会在终端提示）。在 **/settings** 配置并测试 CLI。

`npm run dev` 会自动启动 Postgres（`localhost:5433`）并设置 `DATABASE_URL` — 无需为数据库编辑 `.env`。

> 设计上无身份验证 — **请勿暴露到公网**。请在 localhost 运行，
> 或在带身份验证的 VPN/代理之后运行。

### 其他命令

| 命令 | 作用 |
|------|------|
| `npm run dev` | 本地应用 + Docker 中的 Postgres（默认） |
| `npm run docker:db` | 仅 Postgres（前台） |
| `npm run docker:up` | Docker 完整栈（API 密钥；主机 CLI **不可用**） |

## 配置 CLI

1. 在终端安装 CLI（`claude`、`codex`、`gemini`、`deepseek-tui`）。
2. 分别完成认证（`claude auth login`、`codex login` 等）。
3. 打开 **/settings**，点击 **Test** 并确认响应。

或在 `.env` 中使用 API 密钥作为备用（在 /settings 中取消勾选 "Prefer local CLIs"）。

## 功能详解

### 模式
- **顺序模式**（勾选 "Wait for each other"）：每个 AI 能看到同一轮中
  前一位的发言。
- **并行模式**（未勾选）：所有 AI 同时发言，各自看到轮次开始时的状态。
  更快，但不太像「对话」。

### 每个 AI 可控制
- 模型（可编辑列表 + 自定义选项）。
- 是否在对话中**激活**。
- 是否**可以提问 / 交流想法**（改变提示词行为）。
- 可选人设。

### 工具
- **Web**：`web_search`（若设置了 `TAVILY_API_KEY` 则使用 Tavily，否则 DuckDuckGo）
  与 `web_fetch`（读取 URL 文本）。
- **Apify**：`apify_run` 运行 Actor 并返回数据集项（需要
  `APIFY_TOKEN`）。
- **MCP**：在 `mcp_servers.json` 中配置的服务器将成为
  AI 可用的工具。

### 记分板（按 AI，实时）
输入/输出 Token、**预估成本**（美元）、已完成**轮次**
及**工具**（调用次数）。另有总计卡片。

## 架构

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

实时通信使用 WebSocket（`/ws/{id}`）。服务端事件：
`snapshot`、`status`、`round`、`turn_start`、`message`、`agent_step`、
`scoreboard`、`log`、`error`。

## 配置 MCP

编辑 `mcp_servers.json`：

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

创建对话时，在工具下勾选 **MCP**。（PATH 中需要 Node/npx。）

## 手动运行（不使用 npm run dev）

需要可访问的 Postgres。Docker DB 已运行时（`npm run docker:db`）：

```bash
pip install -r requirements.txt
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/aicouncil uvicorn app.main:app --reload
```

## 诚实说明

- `catalog.py` 中的**价格与模型名称**仅为起点且经常变化 —
  请核实并编辑。「成本」为**估算值**。
- **MCP** 是最依赖环境的部分。已实现且隔离
  （失败不会导致应用崩溃），但请用你实际使用的服务器验证。
- **Stop** 在轮次边界中断；已在进行的轮次
  会先完成（工具有超时）。
- **CLI 模式**（通过 `npm run dev`）不为 AI 使用 Web/Apify/MCP 工具 —
  仅文本。要使用工具，请用 API 密钥或 `npm run docker:up`。

## 许可证

Copyright © 2026 Sólon Abuquerque。根据 [MIT 许可证](LICENSE) 发布。

---

## 关键词

人们用来搜索此类项目的术语：

**English:** multi-agent AI, AI debate, AI council, LLM orchestration, multi-model chat, Claude ChatGPT Gemini together, AI collaboration tool, self-hosted AI platform, real-time AI dashboard, AI cost tracker, token usage scoreboard, human-in-the-loop AI, AI synthesis, parallel AI agents, sequential AI debate, MCP tools for LLMs, FastAPI WebSocket AI, PostgreSQL AI conversations, local AI CLI, OpenAI Anthropic Google DeepSeek

**Português:** debate entre IAs, conselho de inteligência artificial, múltiplos agentes IA, orquestração de LLM, Claude ChatGPT Gemini juntos, ferramenta de colaboração IA, plataforma IA self-hosted, painel IA em tempo real, controle de custo IA, scoreboard de tokens, humano no loop, síntese com IA, agentes IA paralelos, debate sequencial IA, ferramentas MCP para LLM, conversas IA PostgreSQL, CLI local IA

**Español:** debate entre IAs, consejo de inteligencia artificial, múltiples agentes IA, orquestación de LLM, Claude ChatGPT Gemini juntos, herramienta de colaboración IA, plataforma IA self-hosted, panel IA en tiempo real, control de costos IA, marcador de tokens, humano en el bucle, síntesis con IA, agentes IA en paralelo, debate secuencial IA, herramientas MCP para LLM, conversaciones IA PostgreSQL, CLI local IA

**中文:** 多智能体 AI, AI 辩论, AI 理事会, 大语言模型编排, 多模型对话, Claude ChatGPT Gemini 一起, AI 协作工具, 自托管 AI 平台, 实时 AI 仪表盘, AI 成本追踪, Token 用量记分板, 人在回路 AI, AI 综合结论, 并行 AI 智能体, 顺序 AI 辩论, LLM 的 MCP 工具, FastAPI WebSocket AI, PostgreSQL AI 对话, 本地 AI CLI, OpenAI Anthropic Google DeepSeek
