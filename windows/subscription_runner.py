"""One ChatGPT-subscription Codex player versus native XMage Mad, isolated locally."""

import argparse
import hashlib
import json
import re
import socket
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from windows import local_smoke as local
from windows import paths
from windows import subscription_client as player
from windows.game_tool_gateway import GameToolGateway
from windows.jsonl import read_complete_events
from windows.mcp_client import rpc

ROOT = paths.LOCAL_ROOT
WINDOWS = paths.WINDOWS

PROMPT = (
    "You are Astra, the player in a live Magic: The Gathering game against native XMage Mad AI. Play the "
    "ENTIRE game to win using only the mage MCP tools. This is a feasibility test, not a coding task. Do not "
    "implement anything or inspect files. You have no shell, browser, file tools, or other game connection. "
    "No other person supplies your moves.\n\n"
    "Public experiment facts: Two Player Duel, Limited deck validation, 20 starting life. Both players have "
    "the same artificial 40-card deck: 20 Island and 20 Slither Blade (U, 1/2, can't be blocked). Normal "
    "shuffling; hands and draw order are hidden. You are requested as the player who chooses play/draw. Your "
    "opponent is Mad. Decide strategy yourself from the legal observations. No outside strategic coach will "
    "intervene.\n\n"
    "Start with get_action_choices, inspect get_game_state when useful, then choose legal actions. Continue "
    "making tool calls until the bridge reports game over. Do NOT finish after a summary or a few moves; "
    "completing the full live game is the task. Do not concede merely to finish the test. Avoid chat and "
    "commentary overhead; prioritize play.\n\n"
    "Interface guide: choose_action responds to the CURRENT pending choice. Use card IDs or indexes exactly "
    "as provided. yes means mulligan/confirm, no means keep/pass when applicable. Play a land in your main "
    "phase if appropriate. Auto-tap pays spell costs; mana_plan is optional. Batch attackers can be 'all' or "
    "comma-separated IDs, blockers can be comma-separated blocker:attacker pairs. Never invent a card ID. If "
    "an action returns an error, refresh choices and correct it. Observe stale state/board cursors. "
    "pass_priority blocks until the next decision; use it instead of polling repeatedly when there is "
    "nothing to do. With until you can advance to a named step, but always respond to combat and "
    "non-priority decisions. Study tool descriptions for exact details.\n\n"
    "Your only information source is your own bridge. You may use public game log/history and oracle text. "
    "Opponent hand identities and library order must remain unknown. Once the game is terminal, output a "
    "short factual result and stop.\n"
)


def launch_human_gui(env, common_arguments, table_id, deck, run, log_file):
    support = paths.LOCAL_ROOT / "support"
    classpath = str(support / "classes") + ";" + (support / "gui-classpath.txt").read_text().strip()
    arguments = [
        *common_arguments,
        "-Xmx1536m",
        "-Dxmage.fullScreen=false",
        "-Dxmage.aiPuppeteer.autoConnect=true",
        "-Dxmage.aiPuppeteer.autoStart=false",
        f"-Dexperiment.tableId={table_id}",
        f"-Dexperiment.deck={deck.as_posix()}",
        "-cp",
        classpath,
        "experiment.HumanGui",
    ]
    args_file = run / "human-gui.args"
    args_file.write_text(
        "\n".join('"' + arg.replace("\\", "/").replace('"', '\\"') + '"' for arg in arguments), encoding="utf-8"
    )
    gui_env = env | {"XMAGE_AI_PUPPETEER_USER": "You", "XMAGE_AI_PUPPETEER": "0"}
    return subprocess.Popen(
        [str(local.JDK / "bin/java.exe"), "@" + str(args_file)],
        cwd=local.REPO / "Mage.Client",
        env=gui_env,
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int)
    parser.add_argument("--choosing-player", choices=("Astra", "Mad", "You"))
    parser.add_argument("--swap-seats", action="store_true")
    parser.add_argument(
        "--human-opponent", action="store_true", help="Open the normal XMage player window for You versus ChatGPT"
    )
    args = parser.parse_args()
    args.timeout = args.timeout or (7200 if args.human_opponent else 1200)
    args.choosing_player = args.choosing_player or ("You" if args.human_opponent else "Astra")
    if args.choosing_player not in {"Astra", "You" if args.human_opponent else "Mad"}:
        parser.error("The choosing player must be in this game")
    run = (
        ROOT
        / ("outputs/gui-sessions" if args.human_opponent else "outputs/subscription-runs")
        / datetime.now(UTC).strftime("run_%Y%m%d_%H%M%S_UTC")
    )
    run.mkdir(parents=True)
    prompt = PROMPT.replace(
        "You are requested as the player who chooses play/draw.",
        f"{args.choosing_player} is requested as the player who chooses play/draw.",
    )
    if args.human_opponent:
        prompt = prompt.replace("native XMage Mad AI", "a human named You using the normal XMage GUI").replace(
            "Your opponent is Mad.", "Your opponent is the human player named You."
        )
        prompt += (
            "\nThe human may take time to think or learn the interface. Wait with pass_priority as appropriate; "
            "do not concede or stop simply because the human has not acted yet. Never supply the human's moves.\n"
        )
    (run / "player-prompt.txt").write_text(prompt, encoding="utf-8")
    print(f"Subscription test logs: {run}", flush=True)
    deck = WINDOWS / "decks/mirror-slither.dck"
    start = time.monotonic()
    manifest = {
        "status": "starting",
        "model_requested": player.MODEL,
        "reasoning_effort": "medium",
        "auth": "existing Codex ChatGPT login; forced_login_method=chatgpt",
        "provider_api_keys": False,
        "api_cost_usd": 0.0,
        "subscription_cost_usd": None,
        "source_commit": local.COMMIT,
        "deck": str(deck),
        "deck_sha256": hashlib.sha256(deck.read_bytes()).hexdigest(),
        "started_at_utc": datetime.now(UTC).isoformat(),
        "choosing_player_requested": args.choosing_player,
        "seats_swapped": args.swap_seats,
        "human_gui": args.human_opponent,
        "shuffling": "normal engine randomness; no fixed RNG seed",
        "isolation": {
            "shell_tools": False,
            "browser_tools": False,
            "apps_plugins": False,
            "project_instructions_bytes": 0,
            "player_cwd": str(player.PLAYER_CWD),
            "game_tools": player.TOOLS,
        },
        "limits": {
            "wall_seconds": args.timeout,
            "player_clock_minutes": None if args.human_opponent else 15,
            "mcp_calls": 400,
        },
    }
    processes = []
    logs = []
    gateway = None
    game_start = None
    human_gui = None
    try:
        env = player.clean_env()
        env["JAVA_HOME"] = str(local.JDK)
        env["PATH"] = str(local.JDK / "bin") + ";" + str(local.MAVEN.parent) + ";" + env["PATH"]
        common_arguments = paths.common_java_arguments()
        common = subprocess.list2cmdline(common_arguments)
        port, reservations = local.reserve_ports()
        tree = ET.parse(local.REPO / "Mage.Server/config/config.xml")
        server_element = tree.getroot().find("server")
        assert server_element is not None
        for key, value in {"serverAddress": "127.0.0.1", "port": str(port), "secondaryBindPort": str(port + 8)}.items():
            server_element.set(key, value)
        xml_path = run / "server_config.xml"
        tree.write(xml_path, encoding="utf-8", xml_declaration=True)
        env.update(
            {
                "XMAGE_AI_PUPPETEER": "1",
                "XMAGE_AI_PUPPETEER_SERVER": "127.0.0.1",
                "XMAGE_AI_PUPPETEER_PORT": str(port),
                "XMAGE_AI_PUPPETEER_USER": "test-observer",
                "XMAGE_AI_PUPPETEER_PASSWORD": "",
                "XMAGE_AI_PUPPETEER_DISABLE_WHATS_NEW": "1",
                "XMAGE_AI_PUPPETEER_WINS_NEEDED": "1",
            }
        )
        for sock in reservations:
            sock.close()

        def log(name):
            file = (run / name).open("w", encoding="utf-8")
            logs.append(file)
            return file

        server = local.launch(
            "Mage.Server",
            env | {"MAVEN_OPTS": f"{common} -Xmx1024m -Dxmage.config.path={xml_path.as_posix()}"},
            log("server.log"),
        )
        processes.append(server)
        local.wait_server(server, port)
        print("Server ready", flush=True)
        config = {
            "gameType": "Two Player Duel",
            "deckType": "Limited",
            "players": [
                {"type": "pilot", "name": "Astra", "deck": deck.as_posix()},
                (
                    {"type": "bridge", "name": "You", "deck": deck.as_posix()}
                    if args.human_opponent
                    else {"type": "cpu", "ai": "COMPUTER_MAD", "name": "Mad", "deck": deck.as_posix()}
                ),
            ],
        }
        if args.swap_seats:
            config["players"].reverse()
        local.save_json(run / "config.json", config)
        observer_env = env | {
            "XMAGE_AI_PUPPETEER_PLAYERS_CONFIG": json.dumps(config),
            "XMAGE_AI_PUPPETEER_CHOOSING_PLAYER": args.choosing_player,
            "XMAGE_AI_PUPPETEER_MATCH_TIME_LIMIT": "NONE" if args.human_opponent else "MIN__15",
            "XMAGE_AI_PUPPETEER_MATCH_BUFFER_TIME": "NONE",
            "MAVEN_OPTS": (
                f"{common} -Xmx1536m -Dxmage.observer.noWindow=true "
                f"-Dxmage.observer.gameDir={run.as_posix()} "
                "-Dxmage.aiPuppeteer.autoConnect=true -Dxmage.aiPuppeteer.autoStart=true"
            ),
        }
        observer = local.launch("Mage.Client.Observer", observer_env, log("observer.log"))
        processes.append(observer)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if observer.poll() is not None:
                raise RuntimeError("Observer exited during table setup")
            if f"waiting for {2 if args.human_opponent else 1} bridge client" in (run / "observer.log").read_text(
                encoding="utf-8"
            ):
                break
            time.sleep(1)
        else:
            raise TimeoutError("Observer did not create a waiting table")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            mcp_port = sock.getsockname()[1]
        bridge_env = env | {
            "MAVEN_OPTS": (
                f"{common} -Xmx512m -Dxmage.bridge.server=127.0.0.1 -Dxmage.bridge.port={port} "
                f"-Dxmage.bridge.username=Astra -Dxmage.bridge.keepAlive=true -Dxmage.bridge.mcpPort={mcp_port} "
                f"-Dxmage.bridge.errorlog={(run / 'Astra-errors.log').as_posix()} "
                f"-Dxmage.bridge.bridgelog={(run / 'Astra-bridge.jsonl').as_posix()}"
            )
        }
        bridge = local.launch("Mage.Client.Bridge", bridge_env, log("bridge.log"), keep_stdin=True)
        processes.append(bridge)
        local.wait_server(bridge, mcp_port, timeout=120)
        url = f"http://127.0.0.1:{mcp_port}/mcp"
        init = rpc(
            url,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-controller", "version": "1"},
            },
        )
        assert "result" in init, init
        gateway = GameToolGateway(url, player.TOOLS, run / "player-tools.jsonl")
        probe = player.start(
            "Verify your game tool connection. Discover mage tools and call get_game_state exactly once. "
            "It is normal for no game to be active yet. Report the returned status and stop. Do not call other tools.",
            log("tool-probe-events.jsonl"),
            log("tool-probe-stderr.log"),
            gateway.url,
        )
        processes.append(probe)
        if probe.wait(timeout=120) != 0 or gateway.call_count < 1:
            raise RuntimeError("Subscription tool preflight did not call the game bridge")
        print("Subscription game-tool preflight passed", flush=True)
        if args.human_opponent:
            table_id = re.search(
                r"waiting for 2 bridge client\(s\) to join table ([0-9a-f-]+)", (run / "observer.log").read_text()
            ).group(1)
            human_gui = launch_human_gui(env, common_arguments, table_id, deck, run, log("human-gui.log"))
            processes.append(human_gui)
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                if human_gui.poll() is not None:
                    raise RuntimeError("Human GUI exited during setup; see human-gui.log")
                if "HUMAN_GUI_JOINED" in (run / "human-gui.log").read_text(encoding="utf-8"):
                    break
                time.sleep(1)
            else:
                raise TimeoutError("Human GUI did not join its seat")
            print("Human XMage window joined; your moves are made in that window", flush=True)
        joined = rpc(url, "tools/call", {"name": "join_table", "arguments": {"deck_path": deck.as_posix()}})
        local.save_json(run / "join-result.json", joined)
        if joined.get("error") or joined.get("result", {}).get("isError"):
            raise RuntimeError(f"Bridge table join failed: {joined}")
        local.save_json(run / "codex-command.json", player.command(gateway.url))
        agent = player.start(prompt, log("codex-events.jsonl"), log("codex-stderr.log"), gateway.url)
        processes.append(agent)
        manifest["status"] = "playing"
        manifest["mcp_url"] = gateway.url
        local.save_json(run / "manifest.json", manifest)
        print(f"GPT-6 Astra subscription player started; own bridge {url}", flush=True)
        game_start = time.monotonic()
        last_report = 0
        while time.monotonic() - game_start < args.timeout:
            if human_gui is not None and human_gui.poll() is not None:
                raise RuntimeError("Human GUI closed; stopping this interactive session")
            if server.poll() is not None:
                raise RuntimeError("Server exited during play")
            events = read_complete_events(run / "codex-events.jsonl")
            completed = [event.get("item", {}) for event in events if event.get("type") == "item.completed"]
            if any(item.get("type") in {"command_execution", "file_change", "web_search"} for item in completed):
                raise RuntimeError("Information boundary violation: non-game tool used")
            if gateway.violations:
                raise RuntimeError(f"Disallowed game tools requested: {gateway.violations}")
            if gateway.call_count > 400:
                raise RuntimeError("Pilot tool-call limit exceeded")
            if gateway.call_count >= last_report + 10:
                last_report = gateway.call_count
                print(f"Player made {gateway.call_count} game tool calls", flush=True)
            terminal = [event for event in local.read_events(run) if event.get("type") == "game_over"]
            if terminal:
                manifest["game_over"] = terminal
                break
            if agent.poll() is not None:
                raise RuntimeError(f"Player exited before game over (code {agent.returncode})")
            time.sleep(2)
        else:
            raise TimeoutError("Pilot wall-clock limit exceeded")
        manifest["observer_exit_code"] = observer.wait(timeout=45)
        manifest["player_exit_code"] = agent.wait(timeout=60)
        manifest["game_wall_seconds"] = round(time.monotonic() - game_start, 3)
        trace = read_complete_events(run / "codex-events.jsonl")
        manifest["usage"] = [event["usage"] for event in trace if event.get("type") == "turn.completed"]
        manifest["status"] = (
            "completed"
            if manifest["observer_exit_code"] == 0 and manifest["player_exit_code"] == 0
            else "completion_error"
        )
        print(json.dumps({"status": manifest["status"], "result": terminal, "usage": manifest["usage"]}), flush=True)
        if human_gui is not None:
            manifest["waiting_for_human_window_close"] = True
            local.save_json(run / "manifest.json", manifest)
            print(
                "Game finished. Close the XMage player window when done; the local services will then stop.", flush=True
            )
            human_gui.wait()
        return 0 if manifest["status"] == "completed" else 1
    except Exception as exc:  # noqa: BLE001 - top-level supervisor records the failure and cleans up owned processes
        manifest["status"] = "failed"
        manifest["failure"] = {"class": type(exc).__name__, "message": str(exc)}
        print(f"Test failure: {type(exc).__name__}: {exc}", flush=True)
        return 1
    finally:
        for proc in reversed(processes):
            local.stop_tree(proc)
        for file in logs:
            file.close()
        if gateway:
            manifest["game_tool_calls_including_probe"] = gateway.call_count
            manifest["disallowed_tool_requests"] = gateway.violations
            gateway.close()
        if game_start is not None:
            manifest.setdefault("game_wall_seconds", round(time.monotonic() - game_start, 3))
        trace_path = run / "codex-events.jsonl"
        if trace_path.exists():
            trace = read_complete_events(trace_path)
            manifest["usage"] = [event["usage"] for event in trace if event.get("type") == "turn.completed"] or None
            errors = [event for event in trace if event.get("type") in {"error", "turn.failed"}]
            if errors:
                manifest["model_errors"] = errors
                if "usage limit" in json.dumps(errors).lower():
                    manifest["failure_category"] = "subscription_usage_limit"
        if manifest["status"] == "failed":
            manifest.setdefault("failure_category", "gameplay_harness_failure" if game_start else "setup_failure")
        manifest["cleanup_complete"] = all(proc.poll() is not None for proc in processes)
        manifest["total_wall_seconds"] = round(time.monotonic() - start, 3)
        local.save_json(run / "manifest.json", manifest)


if __name__ == "__main__":
    raise SystemExit(main())
