"""Real gateway HTTP round trips with scripted native responses; no inference."""

import copy
import json
import threading
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from windows.game_tool_gateway import GameToolGateway
from windows.player_view import PlayerView

TOOLS = ["get_action_choices", "choose_action", "pass_priority", "get_game_state", "get_oracle_text", "concede"]
BOARD = [
    {"name": "You", "is_you": True, "life": 40, "hand": [{"id": "p1", "rules": ["Draw a card."]}]},
    {"name": "Opponent", "life": 40, "hand_count": 7},
]


def decision(**changes):
    value = {
        "action_pending": True,
        "action_type": "GAME_SELECT",
        "response_type": "boolean",
        "respond_with": "choice=yes (confirm) or choice=no (pass)",
        "board": copy.deepcopy(BOARD),
        "board_cursor": 1,
        "game_seq": 1,
        "choices": [],
    }
    value.update(changes)
    return value


def envelope(value):
    return {
        "content": [{"type": "text", "text": json.dumps(value)}],
        "structuredContent": copy.deepcopy(value),
        "isError": False,
    }


def value(response):
    result = response["result"]
    parsed = json.loads(result["content"][0]["text"])
    assert parsed == result["structuredContent"]
    return parsed


@pytest.fixture
def serve(tmp_path):
    @contextmanager
    def start(responses):
        remaining = iter(responses)
        received = []

        class Native(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                received.append(request)
                if request["method"] == "tools/list":
                    result = {"tools": [{"name": name, "description": name} for name in TOOLS]}
                else:
                    result = envelope(next(remaining))
                body = json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        native = ThreadingHTTPServer(("127.0.0.1", 0), Native)
        thread = threading.Thread(target=native.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        trace = tmp_path / "trace.jsonl"
        gateway = GameToolGateway(f"http://127.0.0.1:{native.server_port}/mcp", TOOLS, trace, optimize_play=True)
        recorded = threading.Event()
        record_call = gateway.record_call

        def record_and_signal(record):
            record_call(record)
            recorded.set()

        gateway.record_call = record_and_signal
        request_number = 0

        def post(tool, arguments=None):
            nonlocal request_number
            request_number += 1
            recorded.clear()
            payload = {
                "jsonrpc": "2.0",
                "id": request_number,
                "method": "tools/list" if tool == "list" else "tools/call",
                "params": {} if tool == "list" else {"name": tool, "arguments": arguments or {}},
            }
            request = urllib.request.Request(gateway.url, data=json.dumps(payload).encode())
            with urllib.request.urlopen(request, timeout=5) as response:
                decoded = json.loads(response.read())
            if tool != "list":
                assert recorded.wait(timeout=3)
            return decoded

        try:
            yield gateway, post, received, trace
        finally:
            gateway.close()
            native.shutdown()
            native.server_close()
            thread.join(timeout=3)

    return start


def test_model_pass_at_empty_priority_uses_native_blocking_pass_and_returns_real_decision(serve):
    next_action = decision(response_type="select", choices=[{"id": "p1", "action": "cast"}], game_seq=9)
    with serve([decision(), next_action]) as (gateway, post, received, trace):
        post("get_action_choices")
        response = post("choose_action", {"choice": "no"})
        assert received[-1]["params"] == {"name": "pass_priority", "arguments": {}}
        assert value(response)["choices"] == next_action["choices"]
        assert value(response)["game_seq"] == 9
        records = [json.loads(line) for line in trace.read_text().splitlines()]
        assert records[-1]["tool"] == "choose_action"
        assert records[-1]["effective_tool"] == "pass_priority"
        assert gateway.optimization_stats()["batched_pass_attempts"] == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"action_type": "GAME_ASK"},  # Mulligan / other yes-no decision.
        {"action_type": "GAME_TARGET"},
        {"action_type": "GAME_GET_AMOUNT"},
        {"action_type": "GAME_PLAY_MANA"},
        {"response_type": "select", "choices": [{"id": "p1", "action": "cast"}]},
        {"combat_phase": "declare_attackers"},
        {"combat_phase": "declare_blockers"},
        {"action_pending": False},
        {"player_dead": True},
        {"game_over": True},
        {"error": "stale action", "retryable": True},
    ],
)
def test_other_decisions_are_never_rerouted_or_answered_automatically(serve, changes):
    with serve([decision(**changes), {"success": True}]) as (_, post, received, _):
        post("get_action_choices")
        post("choose_action", {"choice": "no"})
        assert received[-1]["params"]["name"] == "choose_action"
        assert len(received) == 2


def test_no_observation_or_additional_action_arguments_cannot_enable_pass_routing(serve):
    with serve([decision(), decision(), decision()]) as (_, post, received, _):
        post("choose_action", {"choice": "no"})
        assert received[-1]["params"]["name"] == "choose_action"
        post("choose_action", {"choice": "no", "attackers": "all"})
        assert received[-1]["params"]["name"] == "choose_action"
        post("choose_action", {"choice": "p1"})
        assert received[-1]["params"]["name"] == "choose_action"


def test_repeated_board_uses_explicit_reference_but_full_snapshot_is_always_recoverable(serve):
    original = decision()
    later = decision(board_cursor=2, game_seq=2, stack=[{"id": "s1", "name": "New spell"}])
    with serve([original, later, later]) as (_, post, received, _):
        first = value(post("get_action_choices"))
        second = value(post("pass_priority", {"board_cursor": 1}))
        assert "board" not in second
        assert second["board_unchanged"] is True
        assert second["board_reference"] == first["board_reference"]
        assert second["board_cursor"] == 2
        assert second["game_seq"] == 2
        assert second["stack"] == later["stack"]
        assert "board_cursor" not in received[-1]["params"]["arguments"]
        full = value(post("get_action_choices", {"board_cursor": 2}))
        assert full["board"] == original["board"]
        assert "board_unchanged" not in full
        assert "board_cursor" not in received[-1]["params"]["arguments"]
        # The model can recover after forgetting/compacting its conversation.
        assert full["board_reference"] == second["board_reference"]


@pytest.mark.parametrize("change", ["life", "rules", "hand_count"])
def test_changed_board_or_rules_always_gets_full_snapshot(serve, change):
    new_board = copy.deepcopy(BOARD)
    if change == "life":
        new_board[0]["life"] = 39
    elif change == "rules":
        new_board[0]["hand"][0]["rules"] = ["Draw two cards."]
    else:
        new_board[1]["hand_count"] = 6
    with serve([decision(), decision(board=new_board)]) as (_, post, _, _):
        first = value(post("get_action_choices"))
        second = value(post("pass_priority"))
        assert second["board"] == new_board
        assert second["board_reference"] != first["board_reference"]
        assert "board_unchanged" not in second
        assert "hand" not in second["board"][1]


def test_snapshot_recovery_when_no_action_is_pending_forces_next_board_to_be_full(serve):
    with serve([decision(), {"action_pending": False}, decision()]) as (_, post, _, _):
        post("choose_action", {"choice": "p1"})
        assert value(post("get_action_choices"))["action_pending"] is False
        recovered = value(post("pass_priority"))
        assert recovered["board"] == BOARD
        assert "board_unchanged" not in recovered


def test_player_caches_are_isolated_and_mismatched_mcp_representations_fail_fast():
    first, second = PlayerView(), PlayerView()
    response = {"result": envelope(decision())}
    first.model_response("choose_action", response)
    unchanged = first.model_response("choose_action", response)
    other_seat = second.model_response("choose_action", response)
    assert "board" not in value(unchanged)
    assert value(other_seat)["board"] == BOARD
    assert response == {"result": envelope(decision())}
    bad = copy.deepcopy(response)
    bad["result"]["structuredContent"]["board"][0]["life"] = 1
    with pytest.raises(ValueError, match="disagree"):
        first.model_response("choose_action", bad)


def test_rpc_error_invalidates_the_previous_priority_observation():
    view = PlayerView()
    view.model_response("get_action_choices", {"result": envelope(decision())})
    view.model_response("choose_action", {"error": {"code": -32603}})
    effective = view.prepare_request({"params": {"name": "choose_action", "arguments": {"choice": "no"}}})
    assert effective["params"]["name"] == "choose_action"


def test_discovery_explains_pass_routing_and_snapshot_recovery(serve):
    with serve([]) as (_, post, _, _):
        tools = {t["name"]: t for t in post("list")["result"]["tools"]}
        assert "pass_priority" in tools["choose_action"]["description"]
        assert "full board" in tools["get_action_choices"]["description"]
        assert "board_reference" in tools["pass_priority"]["description"]


@pytest.mark.parametrize("failure", [TimeoutError, ConnectionResetError])
def test_transport_failure_is_traced_once_and_never_retried(serve, monkeypatch, failure):
    with serve([]) as (gateway, post, received, trace):
        attempts = []

        def fail(request):
            attempts.append(request)
            raise failure("private transport detail must not escape")

        monkeypatch.setattr(gateway, "forward_request", fail)
        response = post("choose_action", {"choice": "p1"})
        assert response["error"]["code"] == -32603
        assert "may already have been applied" in response["error"]["message"]
        assert "private transport detail" not in json.dumps(response)
        records = [json.loads(line) for line in trace.read_text().splitlines()]
        assert len(records) == len(attempts) == 1
        assert records[0]["outcome"] in {"timeout", "transport_error"}
        assert records[0]["request_id"] == 1
        assert received == []


@pytest.mark.parametrize("raw", [b"{", b"{}", b'{"result":null}'])
def test_malformed_native_response_is_fatal_instead_of_triggering_a_model_retry_loop(serve, monkeypatch, raw):
    with serve([]) as (gateway, post, _, trace):
        monkeypatch.setattr(gateway, "forward_request", lambda _request: (200, raw))
        assert post("get_action_choices")["error"]["code"] == -32603
        assert gateway.fatal_error is not None
        record = json.loads(trace.read_text())
        assert record["outcome"] == "invalid_response"
