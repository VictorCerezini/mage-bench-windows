"""OpenRouter-through-OpenCode isolation with fake settings and no model invocation."""

import json
import os
from types import SimpleNamespace

import pytest

from windows import openrouter_client, paths

FAKE_KEY = "test-key-not-a-secret"
MODEL = {
    "id": "google/gemma-4-31b-it:free",
    "name": "Google: Gemma 4 31B (free)",
    "efforts": ["default", "low", "medium", "high"],
    "defaultEffort": "default",
    "isDefault": True,
    "contextLength": 262144,
    "maxOutput": 32768,
}


@pytest.fixture
def fake_local(tmp_path, monkeypatch):
    executable = tmp_path / "opencode.exe"
    executable.write_text("not a real executable")
    monkeypatch.setattr(paths, "settings", lambda: {"opencode_executable": str(executable)})
    monkeypatch.setattr(openrouter_client, "OPENCODE_HOME", tmp_path / "opencode-home")
    monkeypatch.setattr(openrouter_client, "AUTH_PATH", tmp_path / "opencode-home/data/opencode/auth.json")
    monkeypatch.setattr(openrouter_client, "MODELS_PATH", tmp_path / "openrouter-models.json")
    return executable


def listing(*items):
    return {"data": list(items)}


def model_listing(model_id, name, *, price="0", parameters=("tools", "reasoning"), output=("text",)):
    return {
        "id": model_id,
        "name": name,
        "pricing": {"prompt": price, "completion": price},
        "supported_parameters": list(parameters),
        "architecture": {"output_modalities": list(output)},
        "context_length": 131072,
        "top_provider": {"context_length": 131072, "max_completion_tokens": 8192},
    }


def test_config_keeps_builtin_tools_off_and_allows_only_game_tools():
    config = openrouter_client.config("http://127.0.0.1:12345/mcp", MODEL, tool_timeout_seconds=7260)
    assert config["tools"] == {"*": False, "mage_*": True}
    assert config["permission"] == {"*": "deny", "mage_*": "allow", "doom_loop": "allow"}
    assert config["agent"]["mage"]["tools"] == config["tools"]
    assert config["agent"]["mage"]["permission"] == config["permission"]
    assert config["mcp"] == {
        "mage": {
            "type": "remote",
            "url": "http://127.0.0.1:12345/mcp",
            "enabled": True,
            "oauth": False,
            "timeout": 7260000,
        }
    }
    assert config["enabled_providers"] == ["openrouter"]
    assert config["provider"]["openrouter"]["models"][MODEL["id"]]["limit"] == {"context": 262144, "output": 32768}
    assert (config["plugin"], config["instructions"], config["share"]) == ([], [], "disabled")
    assert config["username"] == "player"


def test_command_selects_the_game_agent_and_effort(fake_local):
    command = openrouter_client.command(MODEL["id"], "high")
    assert command[:2] == [str(fake_local), "run"]
    assert command[command.index("--agent") + 1] == "mage"
    assert command[command.index("--model") + 1] == "openrouter/google/gemma-4-31b-it:free"
    assert command[command.index("--variant") + 1] == "high"
    assert "--pure" in command
    # Auto-approval would let an "ask" permission through.
    assert "--auto" not in command
    assert "--variant" not in openrouter_client.command(MODEL["id"], "default")


def test_missing_executable_asks_for_setup(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "settings", lambda: {"opencode_executable": str(tmp_path / "missing.exe")})
    with pytest.raises(RuntimeError, match="OpenCodePath"):
        openrouter_client.command(MODEL["id"])


def test_child_environment_is_isolated_from_the_user_profile(fake_local, monkeypatch):
    for name in openrouter_client.CREDENTIAL_OVERRIDES | {"OPENCODE_CONFIG_CONTENT", "OPENCODE_API_KEY"}:
        monkeypatch.setenv(name, "test-value-not-a-secret")
    cleaned = openrouter_client.clean_env()
    assert not openrouter_client.CREDENTIAL_OVERRIDES & set(cleaned)
    assert "OPENCODE_CONFIG_CONTENT" not in cleaned
    assert "OPENCODE_API_KEY" not in cleaned
    assert os.environ["OPENCODE_API_KEY"] == "test-value-not-a-secret"
    home = openrouter_client.OPENCODE_HOME
    assert cleaned["HOME"] == cleaned["USERPROFILE"] == str(home / "home")
    assert cleaned["XDG_DATA_HOME"] == str(home / "data")
    assert cleaned["XDG_CONFIG_HOME"] == str(home / "config")
    for flag in ("CLAUDE_CODE", "EXTERNAL_SKILLS", "PROJECT_CONFIG", "AUTOUPDATE"):
        assert cleaned[f"OPENCODE_DISABLE_{flag}"] == "1"


def test_start_sends_the_prompt_on_stdin_with_inline_config(fake_local, monkeypatch):
    openrouter_client.MODELS_PATH.write_text(json.dumps({MODEL["id"]: MODEL}))
    written = []
    stdin = SimpleNamespace(write=written.append, close=lambda: None)
    launched = {}

    def popen(cmd, **kwargs):
        launched.update(cmd=cmd, **kwargs)
        return SimpleNamespace(stdin=stdin)

    monkeypatch.setattr(openrouter_client.subprocess, "Popen", popen)
    openrouter_client.start("play", None, None, "http://127.0.0.1:1/mcp", model=MODEL["id"], reasoning="low")
    config = json.loads(launched["env"]["OPENCODE_CONFIG_CONTENT"])
    assert config["mcp"]["mage"]["url"] == "http://127.0.0.1:1/mcp"
    assert launched["cwd"] == paths.PLAYER_CWD
    assert written == [b"play"]


def test_model_missing_from_launch_catalog_is_rejected(fake_local):
    with pytest.raises(ValueError, match="reopen the launcher"):
        openrouter_client.start("play", None, None, model="vanished/model:free")


def tool_event(name, status="completed"):
    return {"type": "tool_use", "part": {"type": "tool", "tool": name, "state": {"status": status}}}


def test_game_tools_and_the_no_op_invalid_tool_are_accepted():
    openrouter_client.require_game_only_events(
        [tool_event("mage_get_game_state"), tool_event("mage_pass_priority"), tool_event("invalid", "error")]
    )


@pytest.mark.parametrize("name", ["bash", "read", "webfetch", "edit", "task", "skill"])
def test_non_game_tools_are_rejected(name):
    with pytest.raises(RuntimeError, match="boundary"):
        openrouter_client.require_game_only_events([tool_event(name, "error")])


def test_usage_totals_step_finish_events():
    step = {
        "type": "step-finish",
        "tokens": {"input": 10, "output": 2, "reasoning": 3, "cache": {"read": 4, "write": 0}},
        "cost": 0,
    }
    events = [{"type": "step_finish", "part": step}, {"type": "step_finish", "part": step}, tool_event("mage_x")]
    assert openrouter_client.usage(events) == [
        {"steps": 2, "input": 20, "output": 4, "reasoning": 6, "cache_read": 8, "cost": 0}
    ]
    assert openrouter_client.usage([]) == []


def test_catalog_lists_only_free_text_models_with_tools():
    catalog = openrouter_client.read_catalog(
        listing(
            model_listing("z/zeta:free", "Zeta (free)"),
            model_listing("a/alpha:free", "Alpha (free)"),
            model_listing("p/paid", "Paid", price="0.000001"),
            model_listing("n/no-tools:free", "No tools (free)", parameters=("reasoning",)),
            model_listing("m/music", "Music", output=("audio",)),
            model_listing("openrouter/free", "Free Models Router"),
        ),
        {"a/alpha:free": ["low", "high"]},
    )
    assert [item["id"] for item in catalog["models"]] == ["a/alpha:free", "z/zeta:free"]
    alpha, zeta = catalog["models"]
    assert alpha["efforts"] == ["default", "low", "high"]
    # A model OpenCode does not know yet still plays, at the provider's default effort.
    assert zeta["efforts"] == ["default"]
    assert (alpha["isDefault"], zeta["isDefault"]) == (True, False)
    assert (alpha["contextLength"], alpha["maxOutput"]) == (131072, 8192)
    assert catalog["id"] == "openrouter_free"


def test_no_free_model_is_an_error():
    with pytest.raises(RuntimeError, match="no free models"):
        openrouter_client.read_catalog(listing(model_listing("p/paid", "Paid", price="1")), {})


def test_opencode_model_listing_is_parsed():
    text = (
        "openrouter/a/alpha:free\n"
        + json.dumps({"id": "a/alpha:free", "variants": {"low": {}, "high": {}}}, indent=2)
        + "\nopenrouter/b/beta:free\n"
        + json.dumps({"id": "b/beta:free", "variants": {}}, indent=2)
        + "\n"
    )
    assert openrouter_client.parse_opencode_models(text) == {"a/alpha:free": ["low", "high"], "b/beta:free": []}


@pytest.mark.parametrize("auth", [None, {}, {"opencode": {"type": "api", "key": FAKE_KEY}}])
def test_missing_openrouter_sign_in_is_reported(fake_local, auth):
    if auth is not None:
        openrouter_client.AUTH_PATH.parent.mkdir(parents=True)
        openrouter_client.AUTH_PATH.write_text(json.dumps(auth))
    with pytest.raises(RuntimeError, match="Sign-In-OpenRouter"):
        openrouter_client.read_key()


def test_discovery_never_copies_the_key_or_account_details(fake_local, monkeypatch):
    openrouter_client.AUTH_PATH.parent.mkdir(parents=True)
    openrouter_client.AUTH_PATH.write_text(json.dumps({"openrouter": {"type": "api", "key": FAKE_KEY}}))
    calls = []

    def get_json(url, key=None):
        calls.append((url, key))
        if url == openrouter_client.KEY_URL:
            return {
                "data": {
                    "label": "private-label",
                    "limit_remaining": 9,
                    "free_model_daily_requests": {"used": 3, "limit": 50, "remaining": 47},
                }
            }
        return listing(model_listing("a/alpha:free", "Alpha (free)"))

    monkeypatch.setattr(openrouter_client, "get_json", get_json)
    monkeypatch.setattr(openrouter_client, "read_opencode_efforts", dict)
    catalog = openrouter_client.discover()
    assert catalog["freeRequestsToday"] == {"used": 3, "limit": 50, "remaining": 47}
    saved = json.dumps(catalog) + openrouter_client.MODELS_PATH.read_text()
    assert FAKE_KEY not in saved
    assert "private-label" not in saved
    # The key goes only to the account endpoint; the public model list is fetched without it.
    assert calls == [(openrouter_client.MODELS_URL, None), (openrouter_client.KEY_URL, FAKE_KEY)]


@pytest.mark.parametrize("selection", [("vanished/model:free", "default"), (MODEL["id"], "xhigh")])
def test_unavailable_model_or_effort_is_rejected(selection):
    with pytest.raises(ValueError, match=r"not in the OpenRouter|does not support"):
        openrouter_client.validate_selection({"models": [MODEL]}, *selection)


def test_failure_reason_reports_the_last_opencode_error_with_a_rate_limit_hint():
    message = "[Google AI Studio] google/gemma-4-31b-it:free is temporarily rate-limited upstream."
    events = [{"type": "error", "error": {"data": {"message": message}}}]
    reason = openrouter_client.failure_reason(events)
    assert reason.startswith(message)
    assert "choose another free model" in reason
    daily = "Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000 free model requests per day"
    reason = openrouter_client.failure_reason([{"type": "error", "error": {"data": {"message": daily}}}])
    assert reason == daily + ". The daily free-model request limit is used up; it resets at midnight UTC."
    assert openrouter_client.failure_reason([tool_event("mage_x")]) is None
    other = [{"type": "error", "error": {"data": {"message": "Model not found"}}}]
    assert openrouter_client.failure_reason(other) == "Model not found"
