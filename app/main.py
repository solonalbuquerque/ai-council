"""Servidor: REST + WebSocket + frontend estático."""
import json
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import store
from app.catalog import PROVIDER_CATALOG
from app.cli_runner import all_statuses, install_provider, launch_login, load_config, save_config, save_token, test_provider
from app.db import init_db
from app.orchestrator import RUNNERS, start_runner
from app.providers import available_providers

load_dotenv()

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
WEB = os.path.join(ROOT, "web")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    app.state.mcp = None
    try:
        cfg = os.path.join(ROOT, "mcp_servers.json")
        servers = []
        if os.path.exists(cfg):
            with open(cfg, encoding="utf-8") as f:
                servers = json.load(f).get("servers", [])
        if servers:
            from app.tools.mcp_bridge import MCPManager
            mgr = MCPManager()
            await mgr.start(servers)
            app.state.mcp = mgr
    except Exception as e:
        print("Init MCP falhou (seguindo sem MCP):", e)
    yield
    if app.state.mcp:
        await app.state.mcp.stop()


app = FastAPI(title="Conselho de IAs", lifespan=lifespan)


# ------------------------------- hub WS -------------------------------
class Hub:
    def __init__(self):
        self.conns: dict[str, set[WebSocket]] = {}

    def join(self, cid: str, ws: WebSocket):
        self.conns.setdefault(cid, set()).add(ws)

    def leave(self, cid: str, ws: WebSocket):
        s = self.conns.get(cid)
        if s:
            s.discard(ws)

    async def broadcast(self, cid: str, message: dict):
        for ws in list(self.conns.get(cid, set())):
            try:
                await ws.send_json(message)
            except Exception:
                self.leave(cid, ws)


hub = Hub()


# ------------------------------- REST ---------------------------------
@app.get("/api/catalog")
async def catalog():
    from app.cli_runner import _in_docker
    in_docker = _in_docker()
    return {
        "available": available_providers(),
        "catalog": PROVIDER_CATALOG,
        "tools": {
            "web": True,
            "apify": bool(os.getenv("APIFY_TOKEN")),
            "mcp": app.state.mcp is not None and len(app.state.mcp.tools) > 0,
        },
        "cli_mode": load_config().get("prefer_cli", True),
        "in_docker": in_docker,
        "runtime_mode": "docker" if in_docker else "local",
    }


@app.get("/api/cli/status")
async def cli_status():
    from app.cli_runner import _in_docker
    in_docker = _in_docker()
    return {
        "providers": await all_statuses(),
        "config": load_config(),
        "runtime_mode": "docker" if in_docker else "local",
    }


@app.post("/api/cli/test/{pkey}")
async def cli_test(pkey: str, payload: dict | None = None):
    prompt = (payload or {}).get("prompt", "OI")
    return await test_provider(pkey, prompt)


@app.post("/api/cli/install/{pkey}")
async def cli_install(pkey: str):
    return await install_provider(pkey)


@app.post("/api/cli/login/{pkey}")
async def cli_login(pkey: str):
    return launch_login(pkey)


@app.post("/api/cli/token/{pkey}")
async def cli_token(pkey: str, payload: dict | None = None):
    return save_token(pkey, (payload or {}).get("token", ""))


@app.put("/api/cli/config")
async def cli_config_update(payload: dict):
    cfg = load_config()
    if "prefer_cli" in payload:
        cfg["prefer_cli"] = bool(payload["prefer_cli"])
    if "extra_paths" in payload:
        cfg["extra_paths"] = list(payload["extra_paths"])
    if "providers" in payload:
        cfg["providers"] = {**cfg.get("providers", {}), **payload["providers"]}
    save_config(cfg)
    return {"ok": True, "config": cfg}


@app.post("/api/conversations")
async def create_conversation(payload: dict):
    cid = await store.create_conversation(payload)
    return {"id": cid}


@app.get("/api/conversations")
async def list_conversations():
    return await store.list_conversations()


@app.get("/api/conversations/{cid}")
async def get_conversation(cid: str):
    full = await store.get_conversation_full(cid)
    if not full:
        return JSONResponse({"error": "not found"}, status_code=404)
    return full


# ------------------------------- WS -----------------------------------
@app.websocket("/ws/{cid}")
async def ws_endpoint(websocket: WebSocket, cid: str):
    await websocket.accept()
    hub.join(cid, websocket)

    async def emit(type_: str, payload: dict, _cid=cid):
        await hub.broadcast(_cid, {"type": type_, "payload": payload})

    try:
        full = await store.get_conversation_full(cid)
        if full:
            await websocket.send_json({"type": "snapshot", "payload": full})

        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            r = RUNNERS.get(cid)

            if action == "start":
                mcp_tools = app.state.mcp.tools if app.state.mcp else []
                await start_runner(cid, emit, mcp_tools)
            elif action == "pause" and r:
                r.pause()
            elif action == "resume" and r:
                r.resume()
            elif action == "stop" and r:
                r.stop()
            elif action == "human":
                text = (data.get("text") or "").strip()
                if text:
                    m = await store.save_message(cid, 0, "human", "Humano", "human", text)
                    await hub.broadcast(cid, {"type": "message", "payload": m})
                    if r:
                        r.add_human(text)
    except WebSocketDisconnect:
        hub.leave(cid, websocket)
    except Exception:
        hub.leave(cid, websocket)


# ---------------------------- frontend --------------------------------
@app.get("/")
async def index():
    return FileResponse(os.path.join(WEB, "index.html"))


@app.get("/settings")
async def settings_page():
    return FileResponse(os.path.join(WEB, "settings.html"))


app.mount("/static", StaticFiles(directory=WEB), name="static")
