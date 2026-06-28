# Conselho de IAs — v2

Plataforma onde várias IAs (Claude, ChatGPT, Gemini, DeepSeek) **debatem em tempo
real** para resolver um problema, com ferramentas (web, Apify, MCP), placar de
custo por IA, terminais ao vivo mostrando cada uma trabalhando e participação
humana no chat. Tudo persistido em PostgreSQL. Sem login.

## Subir (recomendado — CLIs locais)

O app roda **na sua máquina** (acessa os CLIs instalados) e só o Postgres sobe no Docker:

```bash
cp .env.example .env        # opcional: ferramentas e fallback de API keys
npm run dev
```

Acesse **http://localhost:8000** (ou **8002** se a 8000 estiver ocupada — o script avisa no terminal). Configure e teste os CLIs em **/settings**.

O `npm run dev` sobe o Postgres automaticamente (`localhost:5433`) e define `DATABASE_URL` — não precisa editar o `.env` para o banco.

> Sem autenticação por design — **não exponha na internet**. Rode em localhost
> ou atrás de uma VPN/proxy com autenticação.

### Outros comandos

| Comando | O que faz |
|---------|-----------|
| `npm run dev` | App local + Postgres no Docker (padrão) |
| `npm run docker:db` | Só Postgres (foreground) |
| `npm run docker:up` | Stack completa no Docker (API keys; CLIs do host **não** funcionam) |

## Configurar CLIs

1. Instale os CLIs no seu terminal (`claude`, `codex`, `gemini`, `deepseek-tui`).
2. Autentique cada um (`claude auth login`, `codex login`, etc.).
3. Abra **/settings**, clique **Testar OI** e confirme a resposta.

Ou use chaves de API no `.env` como fallback (desmarque "Preferir CLIs locais" em /settings).

## Como funciona

1. **+ Nova conversa**: defina objetivo, nº de rodadas, orçamento de tokens,
   modo (sequencial ou paralelo), ferramentas e quais IAs participam (com modelo
   e persona de cada uma).
2. **Iniciar**: as IAs falam em rodadas. No fim, uma faz a **síntese**.
3. Você pode **Pausar/Retomar/Parar** e **entrar no chat como humano** a qualquer
   momento — sua mensagem entra na conversa na próxima vez que uma IA for falar.

### Modos
- **Sequencial** (checkbox "Aguardar uns aos outros" marcado): cada IA vê o que a
  anterior disse na mesma rodada.
- **Paralelo** (desmarcado): todas falam ao mesmo tempo, cada uma vendo o estado
  no início da rodada. Mais rápido, menos "conversa".

### Por IA, você controla
- Modelo (lista editável + opção customizada).
- Se está **ativa** na conversa.
- Se **pode perguntar / trocar ideias** (muda o comportamento no prompt).
- Persona opcional.

### Ferramentas
- **Web**: `web_search` (usa Tavily se houver `TAVILY_API_KEY`, senão DuckDuckGo)
  e `web_fetch` (lê o texto de uma URL).
- **Apify**: `apify_run` roda um Actor e devolve itens do dataset (precisa
  `APIFY_TOKEN`).
- **MCP**: servidores configurados em `mcp_servers.json` viram ferramentas
  disponíveis para as IAs.

### Placar (por IA, em tempo real)
Tokens de entrada/saída, **gasto estimado** (USD), **prontos** (turnos
concluídos) e **ferramentas** (chamadas). Mais um card de total.

## Arquitetura

```
app/
  main.py          FastAPI: REST + WebSocket + serve o frontend
  db.py            engine async (SQLAlchemy 2.0 + asyncpg)
  models.py        Conversation, Participant, Message, UsageEvent
  store.py         acesso ao banco + agregação do placar
  catalog.py       modelos por provedor + tabela de preços (EDITE)
  providers.py     adaptadores com loop de ferramentas (OpenAI-compat + Anthropic)
  orchestrator.py  motor: rodadas, sequencial/paralelo, humano, orçamento, síntese
  tools/           web, apify, mcp_bridge
web/               index.html, styles.css, app.js (control room em tempo real)
```

A comunicação em tempo real é por WebSocket (`/ws/{id}`). Eventos do servidor:
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

Na criação da conversa, marque **MCP** nas ferramentas. (Node/npx necessário no PATH.)

## Rodar manualmente (sem npm run dev)

Precisa de um Postgres acessível. Com o banco Docker já rodando (`npm run docker:db`):

```bash
pip install -r requirements.txt
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/aicouncil uvicorn app.main:app --reload
```

## Avisos honestos

- **Preços e nomes de modelo** em `catalog.py` são pontos de partida e mudam com
  frequência — confirme e edite. O "gasto" é **estimativa**.
- **MCP** é a parte mais dependente do seu ambiente. Vem implementada e isolada
  (falhas não derrubam o app), mas valide com os servidores que você usar.
- **Parar** interrompe na fronteira entre turnos; um turno já em andamento
  termina antes (há timeout nas ferramentas).
- **Modo CLI** (via `npm run dev`) não usa ferramentas web/Apify/MCP nas IAs —
  apenas texto. Para ferramentas, use API keys ou `npm run docker:up`.
