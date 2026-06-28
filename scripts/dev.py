#!/usr/bin/env python3
"""Sobe Postgres no Docker e roda o app localmente (acessa CLIs do host)."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5433/aicouncil"
DB_HOST = "127.0.0.1"
DB_PORT = 5433
APP_HOST = "127.0.0.1"
APP_PORTS = [8000, 8002]
WAIT_TIMEOUT = 60


def log(msg: str) -> None:
    print(msg, flush=True)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, **kwargs)


def docker_ok() -> bool:
    try:
        r = run(["docker", "compose", "version"], capture_output=True, text=True)
        return r.returncode == 0
    except FileNotFoundError:
        return False


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def wait_for_db() -> bool:
    log(f"Aguardando Postgres em {DB_HOST}:{DB_PORT}…")
    deadline = time.time() + WAIT_TIMEOUT
    while time.time() < deadline:
        if port_open(DB_HOST, DB_PORT):
            log("Postgres pronto.")
            return True
        time.sleep(1)
    return False


def start_db() -> None:
    log("Subindo Postgres (docker compose up db -d)…")
    r = run(["docker", "compose", "up", "db", "-d"], text=True)
    if r.returncode != 0:
        log("Erro ao subir o banco. Verifique se o Docker está rodando.")
        sys.exit(1)


def ensure_python_deps() -> None:
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        log("Instalando dependências Python…")
        r = run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"])
        if r.returncode != 0:
            log("Falha ao instalar requirements.txt. Rode: pip install -r requirements.txt")
            sys.exit(1)


def pick_app_port() -> int:
    for port in APP_PORTS:
        if not port_open(APP_HOST, port):
            return port
    return APP_PORTS[-1]


def main() -> None:
    os.chdir(ROOT)

    if not docker_ok():
        log("Docker não encontrado. Instale Docker Desktop e tente novamente.")
        sys.exit(1)

    ensure_python_deps()
    start_db()

    if not wait_for_db():
        log(f"Timeout: Postgres não respondeu em {DB_HOST}:{DB_PORT} após {WAIT_TIMEOUT}s.")
        log("Verifique: docker compose logs db")
        sys.exit(1)

    env = os.environ.copy()
    env["DATABASE_URL"] = DATABASE_URL

    # dotenv para o restante (.env) sem sobrescrever DATABASE_URL
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
        env.setdefault("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_API_KEY", ""))
    except ImportError:
        pass
    env["DATABASE_URL"] = DATABASE_URL

    app_port = pick_app_port()
    if app_port != APP_PORTS[0]:
        log(f"Aviso: porta {APP_PORTS[0]} ocupada — usando {app_port}.")

    log("")
    log("=" * 50)
    log(f"  App:      http://{APP_HOST}:{app_port}")
    log(f"  CLIs:     http://{APP_HOST}:{app_port}/settings")
    log(f"  Postgres: {DB_HOST}:{DB_PORT} (Docker)")
    log("=" * 50)
    log("")

    cmd = [
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--reload",
        "--host", APP_HOST,
        "--port", str(app_port),
    ]
    try:
        subprocess.run(cmd, cwd=ROOT, env=env)
    except KeyboardInterrupt:
        log("\nEncerrado.")


if __name__ == "__main__":
    main()
