"""Encerra todos os servidores ai-council (uvicorn/dev.py) nas portas locais."""
import sys
import time
import os

try:
    import psutil
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "psutil"])
    import psutil

PORTS = {8002, 8010, 8020, 8080, 8765}
killed: set[int] = set()


def kill_tree(pid: int) -> None:
    if not pid or pid in killed:
        return
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    for child in proc.children(recursive=True):
        kill_tree(child.pid)
    try:
        print(f"kill {pid}: {' '.join(proc.cmdline() or [])[:140]}")
        proc.kill()
        killed.add(pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        print(f"  skip {pid}: {e}")


def main() -> None:
    my_pid = os.getpid()

    # Workers órfãos do uvicorn (--reload)
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmd = " ".join(proc.info["cmdline"] or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        pid = proc.info["pid"]
        if pid == my_pid or pid in killed:
            continue
        if any(x in cmd for x in ("uvicorn app.main", "WatchFiles", "scripts/dev.py", "multiprocessing.spawn")):
            if "ai-council" in cmd.lower() or "aicouncil" in cmd.lower() or "multiprocessing.spawn" in cmd:
                kill_tree(pid)

    # Por porta
    for conn in psutil.net_connections(kind="inet"):
        if conn.status != psutil.CONN_LISTEN or not conn.laddr:
            continue
        if conn.laddr.port not in PORTS:
            continue
        kill_tree(conn.pid or 0)

    # Por comando
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmd = " ".join(proc.info["cmdline"] or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        low = cmd.lower()
        if proc.info["pid"] in killed:
            continue
        if ("ai-council" in low or "aicouncil" in low) and any(
            x in low for x in ("uvicorn", "dev.py", "watchfiles")
        ):
            kill_tree(proc.info["pid"])

    time.sleep(2)
    print("\nPortas:")
    for port in sorted(PORTS):
        owners = [
            c.pid
            for c in psutil.net_connections(kind="inet")
            if c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port == port
        ]
        print(f"  :{port} -> {'livre' if not owners else owners}")


if __name__ == "__main__":
    main()
