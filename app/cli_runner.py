"""Detecção, teste e execução de CLIs locais."""
import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

from app.cli_registry import CLI_SPECS, PKEY_ORDER

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "cli_config.json"

DEFAULT_CONFIG = {
    "prefer_cli": True,
    "extra_paths": [],
    "providers": {},
}

PING_TIMEOUT = 90
INSTALL_TIMEOUT = 300

API_KEY_VARS = [
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "DEEPSEEK_API_KEY",
]


def clean_cli_env(env: dict) -> dict:
    """Remove chaves de API vazias para o CLI usar login nativo (OAuth ~/.claude etc.)."""
    env = dict(env)
    for k in API_KEY_VARS:
        if k in env and not str(env[k]).strip():
            del env[k]
    return env


def _inject_tokens(env: dict) -> dict:
    """Injeta tokens salvos (ex.: CLAUDE_CODE_OAUTH_TOKEN) no ambiente do CLI."""
    providers = load_config().get("providers", {})
    for pkey, spec in CLI_SPECS.items():
        token_env = spec.get("token_env")
        if not token_env:
            continue
        token = (providers.get(pkey, {}) or {}).get("token")
        if not (token and str(token).strip()):
            continue
        value = str(token).strip()
        envs = token_env if isinstance(token_env, (list, tuple)) else [token_env]
        for ev in envs:
            env[ev] = value
    return env


def build_cli_env() -> dict:
    env = clean_cli_env(os.environ.copy())
    extra = _search_paths()
    if extra:
        env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])
    env = _inject_tokens(env)
    return env


def save_token(pkey: str, token: str | None) -> dict:
    """Salva (ou limpa) o token do provedor no cli_config.json."""
    spec = CLI_SPECS.get(pkey)
    if not spec:
        return {"ok": False, "message": "Provedor desconhecido"}
    if not spec.get("token_env"):
        return {"ok": False, "message": "Este provedor não usa token."}

    cfg = load_config()
    providers = cfg.setdefault("providers", {})
    prov = providers.setdefault(pkey, {})
    token = (token or "").strip()
    if token:
        prov["token"] = token
        msg = "Token salvo. Clique em Testar."
    else:
        prov.pop("token", None)
        msg = "Token removido."
    save_config(cfg)
    return {"ok": True, "message": msg, "has_token": bool(token)}


def _in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                data = json.load(f)
            merged = {**DEFAULT_CONFIG, **data}
            merged["providers"] = {**DEFAULT_CONFIG["providers"], **data.get("providers", {})}
            return merged
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def _search_paths() -> list[str]:
    paths = []
    env = os.getenv("CLI_EXTRA_PATH", "")
    if env:
        paths.extend(p.strip() for p in env.split(os.pathsep) if p.strip())
    if os.name == "nt":
        agy_bin = os.path.expandvars(r"%LOCALAPPDATA%\agy\bin")
        if agy_bin and agy_bin not in paths:
            paths.append(agy_bin)
    cfg = load_config()
    for p in cfg.get("extra_paths") or []:
        if p and p not in paths:
            paths.append(p)
    return paths


def resolve_command(pkey: str) -> tuple[str | None, str | None]:
    """Retorna (comando, caminho absoluto ou None)."""
    spec = CLI_SPECS.get(pkey)
    if not spec:
        return None, None

    cfg = load_config().get("providers", {}).get(pkey, {})
    if cfg.get("command"):
        cmd = cfg["command"]
        if os.path.isfile(cmd):
            return cmd, cmd
        found = shutil.which(cmd, path=_path_env())
        return (found, found) if found else (cmd, None)

    for name in spec["commands"]:
        found = shutil.which(name, path=_path_env())
        if found:
            return name, found
    return None, None


def _path_env() -> str | None:
    extra = _search_paths()
    if not extra:
        return None
    base = os.environ.get("PATH", "")
    return os.pathsep.join(extra + [base])


def _build_ping_argv(pkey: str, cmd: str, prompt: str) -> list[str]:
    if pkey == "claude":
        return [cmd, "-p", prompt, "--output-format", "text", "--tools", ""]
    if pkey == "gpt":
        return [cmd, "exec", "--skip-git-repo-check", prompt]
    if pkey == "gemini":
        return [cmd, "-p", prompt, "--approval-mode", "yolo", "--skip-trust"]
    if pkey == "antigravity":
        return [cmd, "-p", prompt, "--print-timeout", "90s", "--dangerously-skip-permissions"]
    if pkey == "deepseek":
        return [cmd, "-p", prompt]
    return [cmd, "-p", prompt]


def _codex_supports_model(model: str) -> bool:
    """O codex (conta ChatGPT) só aceita modelos próprios; gpt-4o/gpt-4.1 dão 400."""
    m = (model or "").strip().lower()
    return m.startswith(("gpt-5", "o3", "o4", "codex"))


def _build_run_argv(
    pkey: str, cmd: str, system: str, user_prompt: str, model: str | None
) -> tuple[list[str], str | None]:
    """Retorna (argv, stdin_text).

    Quando stdin_text != None, o prompt vai pelo STDIN em vez de argumento de
    linha de comando. Isso é essencial nos wrappers .CMD do Windows (claude,
    codex, gemini): rodados via cmd.exe, qualquer quebra de linha no argumento
    trunca o comando — o CLI recebia só "OBJETIVO:" e perdia objetivo+histórico.
    """
    combined = f"{system}\n\n{user_prompt}"
    if pkey == "claude":
        argv = [cmd, "-p", "--output-format", "text", "--tools", ""]
        if model:
            argv.extend(["--model", model])
        return argv, combined
    if pkey == "gpt":
        argv = [cmd, "exec", "--skip-git-repo-check", "-c", "approval=never"]
        # O codex via conta ChatGPT só aceita modelos próprios (gpt-5*, o3, o4, codex).
        # Modelos de API como gpt-4o causam 400; nesse caso usamos o default da conta.
        if model and _codex_supports_model(model):
            argv.extend(["-c", f"model={model}"])
        return argv, combined
    if pkey == "gemini":
        argv = [cmd, "-p", "", "--approval-mode", "yolo", "--skip-trust"]
        if model:
            argv.extend(["-m", model])
        return argv, combined
    if pkey == "antigravity":
        # agy.EXE roda via argv direto (sem shell), então quebras de linha são preservadas.
        argv = [cmd, "-p", combined, "--print-timeout", "180s", "--dangerously-skip-permissions"]
        if model:
            argv.extend(["--model", model])
        return argv, None
    if pkey == "deepseek":
        argv = [cmd, "-p", combined]
        if model:
            argv.extend(["--model", model])
        return argv, None
    return [cmd, "-p", combined], None


def _classify_error(stderr: str, stdout: str) -> str:
    text = (stderr + stdout).lower()
    if "ineligibletiererror" in text or "unsupported_client" in text:
        return "auth"
    if any(k in text for k in ("authenticate", "authentication", "401", "login", "api key", "auth method", "credentials")):
        return "auth"
    if "command not found" in text or "not recognized" in text:
        return "missing"
    return "error"


def _run_sync(
    argv: list[str], env: dict, timeout: int, stdin_data: str | None = None
) -> tuple[int, str, str]:
    import subprocess

    kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "env": env,
        "cwd": str(ROOT),
        "timeout": timeout,
    }
    if stdin_data is not None:
        kwargs["input"] = stdin_data.encode("utf-8")
    else:
        kwargs["stdin"] = subprocess.DEVNULL
    cmd = argv[0]
    try:
        if os.name == "nt" and cmd.lower().endswith((".cmd", ".bat")):
            proc = subprocess.run(subprocess.list2cmdline(argv), shell=True, **kwargs)
        else:
            proc = subprocess.run(argv, **kwargs)
    except subprocess.TimeoutExpired:
        return -1, "", f"Timeout após {timeout}s"

    stdout = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
    stderr = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
    return proc.returncode or 0, stdout, stderr


async def _run_process(
    argv: list[str], timeout: int = PING_TIMEOUT, stdin_data: str | None = None
) -> tuple[int, str, str]:
    env = build_cli_env()
    return await asyncio.to_thread(_run_sync, argv, env, timeout, stdin_data)


async def get_version(cmd: str, pkey: str) -> str | None:
    spec = CLI_SPECS[pkey]
    code, out, err = await _run_process([cmd, *spec["version_args"]], timeout=15)
    text = (out or err).strip()
    if code == 0 and text:
        return text.split("\n")[0][:120]
    return None


async def provider_status(pkey: str, *, ping: bool = False) -> dict:
    spec = CLI_SPECS[pkey]
    cmd, path = resolve_command(pkey)
    cfg = load_config().get("providers", {}).get(pkey, {})
    install_cmd = spec.get("install_windows") if os.name == "nt" else spec.get("install")
    install_cmd = install_cmd or spec["install"]

    status = {
        "pkey": pkey,
        "label": spec["label"],
        "installed": bool(path),
        "command": cmd,
        "path": path,
        "version": None,
        "authenticated": False,
        "ready": False,
        "status": "missing",
        "message": "",
        "install": install_cmd,
        "install_alt": spec.get("install_alt"),
        "auth_help": spec["auth_help"],
        "enabled": cfg.get("enabled", True),
        "in_docker": _in_docker(),
        "supports_token": bool(spec.get("token_env")),
        "token_hint": spec.get("token_hint"),
        "has_token": bool((cfg.get("token") or "").strip()),
    }

    if not path:
        status["message"] = "CLI não encontrado no PATH."
        return status

    status["version"] = await get_version(path, pkey)
    status["installed"] = True
    status["status"] = "installed"
    status["message"] = "Instalado — clique em Testar para validar autenticação."

    if ping:
        result = await test_provider(pkey)
        status["authenticated"] = result["ok"]
        status["ready"] = result["ok"]
        status["status"] = result["status"]
        status["message"] = result["message"]
        status["last_response"] = result.get("response")

    return status


async def all_statuses(*, ping: bool = False) -> list[dict]:
    return [await provider_status(k, ping=ping) for k in PKEY_ORDER]


async def test_provider(pkey: str, prompt: str | None = None) -> dict:
    spec = CLI_SPECS[pkey]
    cmd, path = resolve_command(pkey)
    if not path:
        return {"ok": False, "status": "missing", "message": "CLI não instalado.", "response": None}

    text = prompt or spec["ping_prompt"]
    argv = _build_ping_argv(pkey, path, text)
    code, stdout, stderr = await _run_process(argv)

    if code == 0 and stdout:
        # Codex inclui metadados antes da resposta — pega últimas linhas úteis
        lines = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
        response = lines[-1] if lines else stdout
        if pkey == "gpt" and len(lines) > 1:
            # resposta costuma ser a última linha após bloco "codex"
            for ln in reversed(lines):
                if ln.lower() not in ("codex", "user", "tokens used") and not ln.startswith("---"):
                    response = ln
                    break
        return {
            "ok": True,
            "status": "ok",
            "message": "CLI autenticado e respondendo.",
            "response": response,
            "raw": stdout[:4000],
        }

    kind = _classify_error(stderr, stdout)
    if kind == "auth":
        raw = (stderr or stdout)[:2000]
        message = f"Precisa autenticar. {spec['auth_help']}"
        if pkey == "gemini" and ("IneligibleTierError" in raw or "UNSUPPORTED_CLIENT" in raw):
            message = (
                "Gemini CLI autenticou no navegador, mas sua conta individual/free tier não é mais "
                "suportada por este cliente. Use conta enterprise/API key compatível ou o card Antigravity CLI."
            )
        return {
            "ok": False,
            "status": "auth",
            "message": message,
            "response": None,
            "raw": raw,
        }

    if pkey == "antigravity" and code == 0 and not stdout and not stderr:
        return {
            "ok": False,
            "status": "auth",
            "message": (
                "O agy não retornou resposta (auth ausente no modo -p). "
                "Faça login, copie a key gerada e cole no campo abaixo, depois Testar."
            ),
            "response": None,
            "raw": "",
        }

    err = stderr or stdout or f"exit code {code}"
    return {
        "ok": False,
        "status": "error",
        "message": err[:500],
        "response": None,
        "raw": (stderr or stdout)[:2000],
    }


async def run_cli(pkey: str, system: str, user_prompt: str, model: str | None = None) -> tuple[str, str | None]:
    """Executa CLI e retorna (texto, erro)."""
    cmd, path = resolve_command(pkey)
    if not path:
        return "", "CLI não disponível"

    argv, stdin_text = _build_run_argv(pkey, path, system, user_prompt, model)
    code, stdout, stderr = await _run_process(argv, timeout=180, stdin_data=stdin_text)

    if code == 0 and stdout:
        # codex exec (lido via stdin) escreve a resposta completa no stdout e os
        # metadados no stderr — então basta retornar o stdout inteiro.
        return stdout.strip(), None

    kind = _classify_error(stderr, stdout)
    if kind == "auth":
        return "", f"CLI não autenticado. {CLI_SPECS[pkey]['auth_help']}"
    return "", (stderr or stdout or "Erro desconhecido")[:800]


async def install_provider(pkey: str) -> dict:
    spec = CLI_SPECS.get(pkey)
    if not spec:
        return {"ok": False, "message": "Provedor desconhecido"}

    install_cmd = spec.get("install_windows") if os.name == "nt" else spec.get("install")
    install_cmd = install_cmd or spec["install"]
    if _in_docker() and install_cmd.startswith("claude install"):
        install_cmd = spec.get("install_alt") or spec["install"]

    def _sync_install() -> tuple[int, str, str]:
        import subprocess
        try:
            proc = subprocess.run(
                install_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=build_cli_env(),
                cwd=str(ROOT),
                timeout=INSTALL_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return -1, "", f"Instalação excedeu {INSTALL_TIMEOUT}s"
        out = (proc.stdout or b"").decode("utf-8", errors="replace")
        err = (proc.stderr or b"").decode("utf-8", errors="replace")
        return proc.returncode or 0, out, err

    code, stdout, stderr = await asyncio.to_thread(_sync_install)
    ok = code == 0

    return {
        "ok": ok,
        "message": "Instalação concluída." if ok else (stderr or stdout or "Falha na instalação")[:800],
        "output": (stdout + stderr)[:4000],
    }


def _build_login_command(pkey: str) -> tuple[str | None, str | None]:
    """Retorna (cmdline para shell, mensagem de erro se CLI ausente)."""
    spec = CLI_SPECS.get(pkey)
    if not spec:
        return None, "Provedor desconhecido"

    _, path = resolve_command(pkey)
    if not path:
        return None, "CLI não instalado."

    import subprocess

    argv = [path, *spec.get("login_args", [])]
    return subprocess.list2cmdline(argv), None


def launch_login(pkey: str) -> dict:
    """Abre terminal nativo do SO com o comando de login do CLI."""
    spec = CLI_SPECS.get(pkey)
    if not spec:
        return {"ok": False, "message": "Provedor desconhecido", "command": None}

    if _in_docker():
        cmdline, _ = _build_login_command(pkey)
        return {
            "ok": False,
            "message": "Login interativo não funciona dentro do Docker. Rode npm run dev na sua máquina.",
            "command": cmdline,
        }

    cmdline, err = _build_login_command(pkey)
    if err:
        return {"ok": False, "message": err, "command": None}

    label = spec["label"]
    env = build_cli_env()
    cwd = str(ROOT)

    import subprocess

    try:
        if os.name == "nt":
            title = f"Login {label}"
            subprocess.Popen(
                f'start "{title}" cmd /k {cmdline}',
                shell=True,
                cwd=cwd,
                env=env,
            )
        elif sys.platform == "darwin":
            script = f'tell application "Terminal" to do script "{cmdline}"'
            subprocess.Popen(["osascript", "-e", script], cwd=cwd, env=env)
        else:
            launched = False
            for term_cmd in (
                ["gnome-terminal", "--", "bash", "-lc", cmdline],
                ["x-terminal-emulator", "-e", f"bash -lc {cmdline!r}"],
                ["konsole", "-e", "bash", "-lc", cmdline],
            ):
                try:
                    subprocess.Popen(term_cmd, cwd=cwd, env=env)
                    launched = True
                    break
                except FileNotFoundError:
                    continue
            if not launched:
                return {
                    "ok": False,
                    "message": "Não foi possível abrir um terminal. Rode o comando manualmente:",
                    "command": cmdline,
                }

        hint = cmdline if spec.get("login_args") else f"{cmdline}  (modo interativo)"
        return {
            "ok": True,
            "message": f"Abrimos um terminal com: {hint}. Conclua o login e clique em Testar.",
            "command": cmdline,
        }
    except Exception as e:
        return {
            "ok": False,
            "message": f"Falha ao abrir terminal: {e}. Rode manualmente:",
            "command": cmdline,
        }


def cli_available(pkey: str) -> bool:
    """Síncrono: CLI instalado (sem testar auth)."""
    _, path = resolve_command(pkey)
    if not path:
        return False
    cfg = load_config().get("providers", {}).get(pkey, {})
    if cfg.get("enabled") is False:
        return False
    if not load_config().get("prefer_cli", True):
        return False
    return True


async def cli_ready(pkey: str) -> bool:
    if not cli_available(pkey):
        return False
    r = await test_provider(pkey)
    return r["ok"]
