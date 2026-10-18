"""Windows-only, CPU-only Mage-Bench smoke test. Never launches an LLM pilot."""

import argparse
import hashlib
import json
import msvcrt
import os
import socket
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

import psutil

from windows import paths
from windows.jsonl import read_complete_events

ROOT = paths.LOCAL_ROOT
REPO = paths.REPO
WINDOWS = paths.WINDOWS
_SETTINGS = paths.settings()
JDK = Path(_SETTINGS["java_home"])
MAVEN = Path(_SETTINGS["maven_path"])
MAVEN_REPOSITORY = Path(_SETTINGS["maven_repository"])
PREFERENCES_JAR = paths.PREFERENCES_JAR
COMMIT = "370e14523fc49b50b42e8af65557a8875490d800"


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def stop_tree(proc):
    if proc.poll() is not None:
        return
    try:
        parent = psutil.Process(proc.pid)
    except psutil.NoSuchProcess:
        return
    descendants = parent.children(recursive=True)
    for child in reversed(descendants):
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    try:
        parent.terminate()
    except psutil.NoSuchProcess:
        pass
    _, alive = psutil.wait_procs([*descendants, parent], timeout=5)
    for child in alive:
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass


def reserve_ports():
    for port in range(18171, 18271):
        sockets = []
        try:
            for candidate in (port, port + 8):
                sock = socket.socket()
                sockets.append(sock)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                sock.bind(("127.0.0.1", candidate))
            return port, sockets
        except OSError:
            for sock in sockets:
                sock.close()
    raise RuntimeError("No free pair of local experiment ports")


def wait_server(proc, port, timeout=240):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"Server exited with {proc.returncode}; see server.log")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(1)
    raise TimeoutError(f"Process did not listen within {timeout} seconds")


def launch(module, env, log_file, *, keep_stdin=False):
    # Raw logs and the real process tree are required for startup checks/cleanup.
    return subprocess.Popen(
        [str(MAVEN), "-q", f"-Dmaven.repo.local={MAVEN_REPOSITORY}", "exec:java"],
        cwd=REPO / module,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE if keep_stdin else subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def check_bridge(env, common, port, run_dir, processes):
    with socket.socket() as probe_socket:
        probe_socket.bind(("127.0.0.1", 0))
        mcp_port = probe_socket.getsockname()[1]
    bridge_env = env | {
        "MAVEN_OPTS": (
            f"{common} -Xmx512m -Dxmage.bridge.server=127.0.0.1 -Dxmage.bridge.port={port} "
            f"-Dxmage.bridge.username=bridge-probe -Dxmage.bridge.keepAlive=true -Dxmage.bridge.mcpPort={mcp_port}"
        )
    }
    started = time.monotonic()
    with (run_dir / "bridge.log").open("w", encoding="utf-8") as log_file:
        bridge = launch("Mage.Client.Bridge", bridge_env, log_file, keep_stdin=True)
        processes.append(bridge)
        try:
            wait_server(bridge, mcp_port, timeout=120)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

            def request(payload):
                req = urllib.request.Request(
                    f"http://127.0.0.1:{mcp_port}/mcp",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with opener.open(req, timeout=20) as response:
                    body = response.read()
                    return json.loads(body) if body else {"http_status": response.status}

            initialized = request(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "windows-local-smoke", "version": "1"},
                    },
                }
            )
            assert "result" in initialized, initialized
            request({"jsonrpc": "2.0", "method": "notifications/initialized"})
            listed = request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            tools = listed["result"]["tools"]
            assert tools, "Bridge returned no tools"
            save_json(run_dir / "bridge-tools.json", listed)
            result = {
                "completed": True,
                "tool_count": len(tools),
                "tool_names": [tool["name"] for tool in tools],
                "wall_seconds": round(time.monotonic() - started, 3),
                "model_api_requests": 0,
                "initialize": initialized,
            }
            save_json(run_dir / "bridge-metrics.json", result)
            print(f"MCP bridge ready: {len(tools)} tools; no model requests", flush=True)
            return result
        finally:
            assert bridge.stdin is not None
            bridge.stdin.close()
            try:
                bridge.wait(timeout=15)
            except subprocess.TimeoutExpired:
                stop_tree(bridge)


def read_events(game_dir):
    return read_complete_events(game_dir / "game_events.jsonl")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, choices=(1, 2), default=2)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--deck", type=Path, default=WINDOWS / "decks/mirror-bears.dck")
    args = parser.parse_args()
    assert os.name == "nt", "This launcher explicitly targets Windows"
    assert MAVEN.is_file() and (JDK / "bin/java.exe").is_file(), "Portable toolchain missing"
    assert PREFERENCES_JAR.is_file(), "Isolated preferences implementation missing"
    run_root = ROOT / "outputs/local-runs"
    run_root.mkdir(parents=True, exist_ok=True)
    with (run_root / "run.lock").open("a+b") as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        return run_locked(args, run_root)


def run_locked(args, run_root):
    started = time.monotonic()
    run_dir = run_root / datetime.now(UTC).strftime("run_%Y%m%d_%H%M%S_UTC")
    run_dir.mkdir()
    print(f"Logs: {run_dir}", flush=True)
    deck = args.deck.resolve(strict=True)
    deck_hash = hashlib.sha256(deck.read_bytes()).hexdigest()
    env = os.environ.copy()
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY"):
        env.pop(key, None)
    env["JAVA_HOME"] = str(JDK)
    env["PATH"] = str(JDK / "bin") + os.pathsep + str(MAVEN.parent) + os.pathsep + env["PATH"]
    common = subprocess.list2cmdline(paths.common_java_arguments())
    port, reservations = reserve_ports()
    config_tree = ET.parse(REPO / "Mage.Server/config/config.xml")
    server_config = config_tree.getroot().find("server")
    assert server_config is not None
    server_config.set("serverAddress", "127.0.0.1")
    server_config.set("port", str(port))
    server_config.set("secondaryBindPort", str(port + 8))
    xml_path = run_dir / "server_config.xml"
    config_tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    env.update(
        {
            "XMAGE_AI_PUPPETEER": "1",
            "XMAGE_AI_PUPPETEER_SERVER": "127.0.0.1",
            "XMAGE_AI_PUPPETEER_PORT": str(port),
            "XMAGE_AI_PUPPETEER_USER": "smoke-observer",
            "XMAGE_AI_PUPPETEER_PASSWORD": "",
            "XMAGE_AI_PUPPETEER_DISABLE_WHATS_NEW": "1",
            "XMAGE_AI_PUPPETEER_WINS_NEEDED": "1",
        }
    )
    manifest = {
        "started_at_utc": datetime.now(UTC).isoformat(),
        "upstream_commit": COMMIT,
        "runner": "standalone Windows launcher of Mage-Bench Java modules",
        "api_mode": False,
        "java_preferences": "isolated in-memory factory; no Windows registry preferences",
        "raw_client_json_logging": False,
        "deck_sha256": deck_hash,
        "deck": str(deck),
        "format": "Limited",
        "shuffling": "normal engine randomness; no fixed RNG seed",
        "server_host": "127.0.0.1",
        "server_port": port,
        "games": [],
    }
    save_json(run_dir / "manifest.json", manifest)
    processes = []
    try:
        for sock in reservations:
            sock.close()
        server_env = env | {"MAVEN_OPTS": f"{common} -Xmx1024m -Dxmage.config.path={xml_path.as_posix()}"}
        with (run_dir / "server.log").open("w", encoding="utf-8") as server_log:
            server = launch("Mage.Server", server_env, server_log)
            processes.append(server)
            wait_server(server, port)
            print(f"Server ready on 127.0.0.1:{port}", flush=True)
            manifest["bridge"] = check_bridge(env, common, port, run_dir, processes)
            save_json(run_dir / "manifest.json", manifest)
            for index in range(args.games):
                choosing_player = ("Mad A", "Mad B")[index]
                game_dir = run_dir / f"game_{index + 1}"
                game_dir.mkdir()
                players = [
                    {"type": "cpu", "ai": "COMPUTER_MAD", "name": name, "deck": deck.as_posix()}
                    for name in ("Mad A", "Mad B")
                ]
                config = {"gameType": "Two Player Duel", "deckType": "Limited", "players": players}
                assert all(player["type"] == "cpu" for player in config["players"])
                save_json(game_dir / "config.json", config)
                game_env = env | {
                    "XMAGE_AI_PUPPETEER_PLAYERS_CONFIG": json.dumps(config, separators=(",", ":")),
                    "XMAGE_AI_PUPPETEER_CHOOSING_PLAYER": choosing_player,
                    "XMAGE_AI_PUPPETEER_MATCH_TIME_LIMIT": "MIN___5",
                    "XMAGE_AI_PUPPETEER_MATCH_BUFFER_TIME": "NONE",
                    "MAVEN_OPTS": (
                        f"{common} -Xmx1536m -Dxmage.observer.noWindow=true "
                        f"-Dxmage.observer.gameDir={game_dir.as_posix()} "
                        "-Dxmage.aiPuppeteer.autoConnect=true -Dxmage.aiPuppeteer.autoStart=true"
                    ),
                }
                game_started = time.monotonic()
                metric = {
                    "game": index + 1,
                    "choosing_player_requested": choosing_player,
                    "players": players,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "api_cost_usd": 0.0,
                    "llm_requests": 0,
                }
                with (game_dir / "observer.log").open("w", encoding="utf-8") as observer_log:
                    observer = launch("Mage.Client.Observer", game_env, observer_log)
                    processes.append(observer)
                    try:
                        metric["observer_exit_code"] = observer.wait(timeout=args.timeout)
                        events = read_events(game_dir)
                        metric["game_over_events"] = [event for event in events if event.get("type") == "game_over"]
                        metric["event_count"] = len(events)
                        metric["completed"] = metric["observer_exit_code"] == 0 and bool(metric["game_over_events"])
                        metric["failure_class"] = None if metric["completed"] else "observer_or_missing_game_over"
                    except subprocess.TimeoutExpired:
                        stop_tree(observer)
                        metric.update(completed=False, failure_class="game_timeout")
                    metric["wall_seconds"] = round(time.monotonic() - game_started, 3)
                    save_json(game_dir / "metrics.json", metric)
                    manifest["games"].append(metric)
                    save_json(run_dir / "manifest.json", manifest)
                    print(json.dumps(metric), flush=True)
                    if not metric["completed"]:
                        return 1
    except Exception as exc:
        manifest["startup_failure"] = {"class": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        for proc in reversed(processes):
            stop_tree(proc)
        manifest["total_wall_seconds"] = round(time.monotonic() - started, 3)
        manifest["cleanup_complete"] = all(proc.poll() is not None for proc in processes)
        save_json(run_dir / "manifest.json", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
