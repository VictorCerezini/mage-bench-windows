"""Exercise the GUI player's lifecycle with fake processes, never a real model."""

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from windows import gui_player


class FakeSocket:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def bind(self, _):
        pass

    def getsockname(self):
        return "127.0.0.1", 12345

    def settimeout(self, _):
        pass

    def connect_ex(self, _):
        return 0


@pytest.fixture
def harness(tmp_path, monkeypatch):
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"models": [{"id": "gpt-6-astra", "efforts": ["medium", "high"]}]}))
    deck = tmp_path / "deck.dck"
    deck.write_text("40 Island\n")
    request = {
        "table_id": "7c134c35-4cbd-4072-a24d-c5d9a2b72987",
        "server_port": 18171,
        "catalog": str(catalog),
        "deck": str(deck),
        "model": "gpt-6-astra",
        "reasoning": "high",
        "seat": 2,
        "game_type": "Two Player Duel",
        "deck_type": "Limited",
        "player_count": 2,
        "owner_pid": os.getpid(),
        "username": "ChatGPT 2",
        "run": str(tmp_path / "run"),
    }
    bridge = SimpleNamespace(poll=lambda: None)
    stopped = []

    def stop(proc):
        stopped.append(proc)
        proc.poll = lambda: 0

    def launch(_module, _env, log, **_kwargs):
        assert f"-Dxmage.bridge.seat={request['seat']}" in _env["MAVEN_OPTS"]
        log.write("[ChatGPT 2] Game over: fake test result\n")
        log.flush()
        return bridge

    runtime = SimpleNamespace(
        JDK=Path("fake-jdk"),
        MAVEN=Path("fake-maven/mvn.cmd"),
        launch=launch,
        stop_tree=stop,
        save_json=lambda path, value: path.write_text(json.dumps(value)),
    )
    gateway = SimpleNamespace(
        url="http://127.0.0.1:12346/mcp",
        violations=[],
        call_count=0,
        fatal_error=None,
        close=lambda: None,
        optimization_stats=lambda: {"policy": "gui-efficient-v1"},
    )
    monkeypatch.setattr(gui_player.socket, "socket", FakeSocket)

    def make_gateway(*_args, **kwargs):
        assert kwargs["optimize_play"] is True
        assert kwargs["upstream_timeout"] > gui_player.MAX_SECONDS
        return gateway

    monkeypatch.setattr(gui_player, "GameToolGateway", make_gateway)
    monkeypatch.setattr(gui_player.time, "sleep", lambda _: None)
    monkeypatch.setattr(gui_player, "check_owner", lambda *_: None)
    return request, runtime, stopped, gateway


def result(value):
    return {"result": {"content": [{"type": "text", "text": json.dumps(value)}]}}


@pytest.mark.parametrize(("players", "seat"), [(2, 2), (4, 3)])
def test_selection_reaches_player_only_after_game_starts(harness, monkeypatch, players, seat):
    request, runtime, stopped, _ = harness
    request.update(
        game_type="Commander Two Player Duel" if players == 2 else "Commander Free For All",
        deck_type="Variant Magic - Commander",
        player_count=players,
        seat=seat,
    )
    observations = iter([False, False, True])
    waiting = []

    def rpc(_url, method, params):
        if method == "initialize":
            return {"result": {}}
        if params["name"] == "get_game_state":
            available = next(observations)
            waiting.append(available)
            return result({"available": available})
        return result({"action_pending": False})

    def start(prompt, out, _err, _url, *, model, reasoning, tool_timeout_seconds):
        assert waiting == [False, False, True]
        assert (model, reasoning) == ("gpt-6-astra", "high")
        assert tool_timeout_seconds == gui_player.MAX_SECONDS + 60
        assert "opponent's deck" in prompt
        assert request["game_type"] in prompt
        assert f"Number of players: {players}" in prompt
        assert "commander selection" in prompt
        out.write(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}) + "\n")
        out.flush()
        return SimpleNamespace(poll=lambda: 0, returncode=0)

    monkeypatch.setattr(gui_player, "rpc", rpc)
    assert gui_player.run_player(request, runtime=runtime, start_player=start) == 0
    manifest = json.loads((Path(request["run"]) / "manifest.json").read_text())
    assert manifest["status"] == "completed"
    assert manifest["cleanup_complete"] is True
    assert manifest["usage"][0]["input_tokens"] == 10
    assert manifest["optimization"]["policy"] == "gui-efficient-v1"
    assert len(stopped) == 2


def test_seat_outside_player_count_is_rejected(harness):
    request, *_ = harness
    request["seat"] = 3
    with pytest.raises(ValueError, match="outside the configured player count"):
        gui_player.validate_request(request)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("[ChatGPT 2] Game over: test", "game_over"),
        ("[ChatGPT 2] Player death detected from game log", "player_eliminated"),
        ("[ChatGPT 3] Player death detected from game log", None),
        ("[ChatGPT 2] Zombie game detected: declaring game dead", None),
        ("[ChatGPT 2] CRITICAL: sendPlayerBoolean failed", None),
    ],
)
def test_only_native_game_end_or_own_elimination_confirms_completion(message, expected):
    assert gui_player.native_terminal_reason(message, "ChatGPT 2") == expected


def test_closing_window_before_start_consumes_no_inference(harness, monkeypatch):
    request, runtime, stopped, _ = harness
    checks = iter([True, True, False])

    def check(*_):
        if not next(checks):
            raise gui_player.SessionCancelledError("test window closed")

    monkeypatch.setattr(gui_player, "check_owner", check)
    monkeypatch.setattr(gui_player, "rpc", lambda *_: result({"available": False, "action_pending": False}))
    start = Mock(side_effect=AssertionError("Inference must not run while waiting"))
    assert gui_player.run_player(request, runtime=runtime, start_player=start) == 0
    manifest = json.loads((Path(request["run"]) / "manifest.json").read_text())
    assert manifest["status"] == "cancelled"
    assert manifest["usage"] == []
    assert manifest["cleanup_complete"] is True
    start.assert_not_called()
    assert len(stopped) == 1


def test_early_player_exit_is_failure_and_cleans_processes(harness, monkeypatch):
    request, runtime, stopped, _ = harness
    monkeypatch.setattr(gui_player, "rpc", lambda *_: result({"available": True}))

    def start(*_args, **_kwargs):
        return SimpleNamespace(poll=lambda: 1, returncode=1)

    assert gui_player.run_player(request, runtime=runtime, start_player=start) == 1
    manifest = json.loads((Path(request["run"]) / "manifest.json").read_text())
    assert manifest["status"] == "failed"
    assert manifest["cleanup_complete"] is True
    assert len(stopped) == 2


@pytest.mark.parametrize("kind", ["command_execution", "file_change", "web_search"])
def test_non_game_tools_are_rejected(kind):
    with pytest.raises(RuntimeError, match="boundary"):
        gui_player.require_game_only_events([{"type": "item.completed", "item": {"type": kind}}])


def test_table_cancellation_stops_player_even_when_window_remains_open(harness):
    request, runtime, stopped, _ = harness
    run = Path(request["run"])
    run.mkdir()
    (run / "cancel.requested").write_text("Table closed")
    start = Mock(side_effect=AssertionError("A cancelled table must not consume inference"))
    assert gui_player.run_player(request, runtime=runtime, start_player=start) == 0
    manifest = json.loads((run / "manifest.json").read_text())
    assert manifest["status"] == "cancelled"
    assert manifest["reason"] == "XMage table was cancelled or left"
    assert manifest["cleanup_complete"] is True
    assert len(stopped) == 1
    start.assert_not_called()


def test_table_cancellation_during_a_blocked_player_wait_still_cleans_both_processes(harness, monkeypatch):
    request, runtime, stopped, _ = harness
    monkeypatch.setattr(gui_player, "rpc", lambda *_: result({"available": True}))

    def cancel_during_play(_events):
        (Path(request["run"]) / "cancel.requested").write_text("Table closed during human wait")

    monkeypatch.setattr(gui_player, "require_game_only_events", cancel_during_play)
    agent = SimpleNamespace(poll=lambda: None)
    start = Mock(return_value=agent)
    assert gui_player.run_player(request, runtime=runtime, start_player=start) == 0
    manifest = json.loads((Path(request["run"]) / "manifest.json").read_text())
    assert manifest["status"] == "cancelled"
    assert manifest["cleanup_complete"] is True
    assert len(stopped) == 2
    start.assert_called_once()
