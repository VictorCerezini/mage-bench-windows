"""Join one GUI-selected table and drive only its ChatGPT seat."""

import importlib
import json
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import psutil

from windows import model_catalog, paths, subscription_client
from windows.game_tool_gateway import GameToolGateway
from windows.jsonl import read_complete_events
from windows.mcp_client import rpc

MAX_CALLS = 2000
MAX_SECONDS = 7200
PROMPT = (
    "You are {username}, playing a live Magic: The Gathering game with a human and possibly other players in XMage. "
    "Play the entire game to win, using only the mage MCP tools. This is a game, not a coding task. "
    "Game mode: {game_type}. Deck format: {deck_type}. Number of players: {player_count}. "
    "Your deck was selected in the match configuration. No assumptions about the opponent's deck, "
    "hand, library order, or which player goes first are justified. Use your own player's observations.\n\n"
    "Start with get_action_choices. Inspect get_game_state and oracle text when useful. Choose legal "
    "actions using the exact card IDs or indexes returned by the bridge. choose_action responds to the "
    "current pending choice. yes/no mean confirm or decline as described by that choice. Auto-tap can "
    "pay mana costs. Batch attackers can be 'all' or comma-separated IDs; blockers can be comma-separated "
    "blocker:attacker pairs. Read tool descriptions for full details. If a choice is stale or an action "
    "returns an error, refresh choices and correct it. Never invent card IDs.\n\n"
    "Use pass_priority to wait for your next decision rather than repeatedly polling. The human may "
    "take time to think; wait patiently. Continue until the bridge reports game_over or player_dead. Do not stop after "
    "a few moves or concede just to finish. Avoid commentary overhead. Do not supply the human's moves "
    "or look for outside information. In multiplayer, inspect all players and legal targets rather than "
    "assuming there is only one opponent. For Commander, respond to commander selection and command-zone "
    "choices using the legal actions provided. Once your game ends or you are eliminated, report your own "
    "factual result briefly and stop; other multiplayer participants may still be playing."
)


class SessionCancelledError(Exception):
    """The owning player window closed; this is not a model loss or harness failure."""


def validate_request(request):
    UUID(request["table_id"])
    if not 1 <= int(request["seat"]) <= int(request["player_count"]):
        raise ValueError("The ChatGPT seat is outside the configured player count")
    if not 1 <= int(request["server_port"]) <= 65535:
        raise ValueError("Invalid local XMage server port")
    if not Path(request["deck"]).is_file():
        raise ValueError("The selected ChatGPT deck file does not exist")
    catalog = json.loads(Path(request["catalog"]).read_text(encoding="utf-8"))
    model_catalog.validate_selection(catalog, request["model"], request["reasoning"])


def tool_payload(response):
    if "error" in response or response["result"].get("isError"):
        raise RuntimeError("The local game bridge rejected a request")
    result = response["result"]
    if "structuredContent" in result:
        return result["structuredContent"]
    return json.loads(next(item["text"] for item in result["content"] if item["type"] == "text"))


def owner_alive(owner, created):
    try:
        return owner.is_running() and owner.create_time() == created
    except psutil.NoSuchProcess:
        return False


def check_owner(owner, created):
    if not owner_alive(owner, created):
        raise SessionCancelledError("XMage player window closed")


def check_session(owner, created, run):
    check_owner(owner, created)
    if (run / "cancel.requested").exists():
        raise SessionCancelledError("XMage table was cancelled or left")


def require_game_only_events(events):
    for event in events:
        if event.get("type") == "item.completed" and event["item"].get("type") in {
            "command_execution",
            "file_change",
            "web_search",
        }:
            raise RuntimeError("Information boundary violation: the player used a non-game tool")


def native_terminal_reason(log_text, username):
    if f"[{username}] Game over: " in log_text:
        return "game_over"
    if f"[{username}] Player death detected from game log" in log_text:
        return "player_eliminated"
    return None


def run_player(request, *, start_player=subscription_client.start, runtime=None):
    if runtime is None:
        runtime = importlib.import_module("windows.local_smoke")

    local = runtime
    validate_request(request)
    run = Path(request["run"])
    run.mkdir(parents=True, exist_ok=True)
    owner = psutil.Process(request["owner_pid"])
    created = owner.create_time()
    manifest = {
        "status": "joining",
        "table_id": request["table_id"],
        "model": request["model"],
        "reasoning": request["reasoning"],
        "seat": request["seat"],
        "game_type": request["game_type"],
        "deck_type": request["deck_type"],
        "player_count": request["player_count"],
        "auth": "existing Codex ChatGPT login",
        "api_mode": False,
        "started_at_utc": datetime.now(UTC).isoformat(),
        "usage": [],
    }
    processes = []
    logs = []
    gateway = None
    started = time.monotonic()

    def log(name):
        stream = (run / name).open("w", encoding="utf-8")
        logs.append(stream)
        return stream

    def save_status(status):
        manifest["status"] = status
        local.save_json(run / "manifest.json", manifest)
        print(status, flush=True)

    try:
        env = subscription_client.clean_env()
        env["JAVA_HOME"] = str(local.JDK)
        env["PATH"] = str(local.JDK / "bin") + ";" + str(local.MAVEN.parent) + ";" + env["PATH"]
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            mcp_port = reservation.getsockname()[1]
        arguments = [
            *paths.common_java_arguments(),
            "-Xmx512m",
            "-Dxmage.bridge.server=127.0.0.1",
            f"-Dxmage.bridge.port={request['server_port']}",
            f"-Dxmage.bridge.username={request['username']}",
            f"-Dxmage.bridge.seat={request['seat']}",
            f"-Dxmage.bridge.deck={Path(request['deck']).as_posix()}",
            f"-Dxmage.bridge.tableId={request['table_id']}",
            f"-Dxmage.bridge.mcpPort={mcp_port}",
            f"-Dxmage.bridge.errorlog={(run / 'bridge-errors.log').as_posix()}",
            f"-Dxmage.bridge.bridgelog={(run / 'bridge.jsonl').as_posix()}",
        ]
        bridge = local.launch(
            "Mage.Client.Bridge",
            env | {"MAVEN_OPTS": subprocess.list2cmdline(arguments)},
            log("bridge.log"),
            keep_stdin=True,
        )
        processes.append(bridge)
        save_status("joining")
        url = f"http://127.0.0.1:{mcp_port}/mcp"
        deadline = time.monotonic() + 180
        while True:
            check_session(owner, created, run)
            if bridge.poll() is not None:
                raise RuntimeError("The ChatGPT game bridge stopped while joining; see bridge.log")
            with socket.socket() as probe:
                probe.settimeout(0.5)
                if probe.connect_ex(("127.0.0.1", mcp_port)) == 0:
                    break
            if time.monotonic() > deadline:
                raise TimeoutError("ChatGPT could not join the selected table within three minutes")
            time.sleep(0.5)
        rpc(
            url,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "gui-controller", "version": "1"},
            },
        )
        save_status("waiting_for_start")
        deadline = time.monotonic() + 600
        while True:
            check_session(owner, created, run)
            if bridge.poll() is not None:
                raise RuntimeError("The ChatGPT bridge stopped before the match started")
            state = tool_payload(rpc(url, "tools/call", {"name": "get_game_state", "arguments": {}}))
            choices = tool_payload(rpc(url, "tools/call", {"name": "get_action_choices", "arguments": {}}))
            if state.get("available") or choices.get("action_pending"):
                break
            if time.monotonic() > deadline:
                raise TimeoutError("The table was not started within ten minutes; create a new match")
            time.sleep(1)
        gateway = GameToolGateway(url, subscription_client.TOOLS, run / "player-tools.jsonl", max_calls=MAX_CALLS)
        prompt = PROMPT.format(
            username=request["username"],
            game_type=request["game_type"],
            deck_type=request["deck_type"],
            player_count=request["player_count"],
        )
        (run / "player-prompt.txt").write_text(prompt, encoding="utf-8")
        agent = start_player(
            prompt,
            log("codex-events.jsonl"),
            log("codex-stderr.log"),
            gateway.url,
            model=request["model"],
            reasoning=request["reasoning"],
        )
        processes.append(agent)
        save_status("playing")
        game_started = time.monotonic()
        while agent.poll() is None:
            check_session(owner, created, run)
            if bridge.poll() is not None:
                raise RuntimeError("The ChatGPT bridge stopped during play")
            if gateway.violations or gateway.call_count > MAX_CALLS:
                raise RuntimeError("The game tool boundary or call limit was exceeded")
            if time.monotonic() - game_started > MAX_SECONDS:
                raise TimeoutError("The interactive game exceeded its two-hour limit")
            require_game_only_events(read_complete_events(run / "codex-events.jsonl"))
            time.sleep(0.5)
        trace = read_complete_events(run / "codex-events.jsonl")
        require_game_only_events(trace)
        manifest["usage"] = [event["usage"] for event in trace if event.get("type") == "turn.completed"]
        terminal_reason = native_terminal_reason((run / "bridge.log").read_text(encoding="utf-8"), request["username"])
        if agent.returncode != 0 or terminal_reason is None:
            raise RuntimeError("ChatGPT stopped before a confirmed game result; see codex-events.jsonl")
        manifest["terminal_reason"] = terminal_reason
        manifest["game_wall_seconds"] = round(time.monotonic() - game_started, 3)
        save_status("completed")
        return 0
    except SessionCancelledError as error:
        manifest["reason"] = str(error)
        save_status("cancelled")
        return 0
    except Exception as error:  # noqa: BLE001 - supervisor records failures and always cleans owned processes
        manifest["error"] = str(error)
        save_status("failed")
        print(f"{type(error).__name__}: {error}", flush=True)
        return 1
    finally:
        for proc in reversed(processes):
            local.stop_tree(proc)
        for stream in logs:
            stream.close()
        if gateway is not None:
            manifest["tool_calls"] = gateway.call_count
            gateway.close()
        events = read_complete_events(run / "codex-events.jsonl")
        manifest["usage"] = [event["usage"] for event in events if event.get("type") == "turn.completed"]
        manifest["total_wall_seconds"] = round(time.monotonic() - started, 3)
        manifest["cleanup_complete"] = all(proc.poll() is not None for proc in processes)
        local.save_json(run / "manifest.json", manifest)


if __name__ == "__main__":
    raise SystemExit(run_player(json.load(sys.stdin)))
