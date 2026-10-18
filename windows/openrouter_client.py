"""OpenRouter free models played through the OpenCode CLI, locked to the mage game tools.

OpenCode runs from its own home under .windows-local, so it never sees your user profile, skills, CLAUDE.md,
or the Claude and ChatGPT sign-ins. The OpenRouter key lives in that home's auth.json, written by
Sign-In-OpenRouter.cmd; it is only ever sent to openrouter.ai and never copied into catalogs or logs.
"""

import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

from windows import paths

PROVIDER = "openrouter_free"
MODELS_URL = "https://openrouter.ai/api/v1/models"
KEY_URL = "https://openrouter.ai/api/v1/key"
# The free router picks a different model for each request, so one game would mix several players.
EXCLUDED_MODELS = {"openrouter/free"}
DEFAULT_EFFORT = "default"
GAME_TOOL_PREFIX = "mage_"
# OpenCode turns a call to a tool that does not exist into its no-op "invalid" tool; nothing runs.
HARMLESS_TOOLS = {"invalid"}
OPENCODE_HOME = paths.LOCAL_ROOT / "opencode-home"
AUTH_PATH = OPENCODE_HOME / "data/opencode/auth.json"
# Context limits of the free models found at launch; the launcher allows one session at a time.
MODELS_PATH = paths.LOCAL_ROOT / "openrouter-models.json"
SYSTEM_PROMPT = (
    "You are a Magic: The Gathering player in a live XMage game. Your only tools are the mage MCP game tools. "
    "This is a game, not a coding task."
)
CREDENTIAL_OVERRIDES = {
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CODEX_API_KEY",
    "CODEX_ACCESS_TOKEN",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
}
# Built-in OpenCode tools stay off and every permission except the game tools is denied. doom_loop is
# allowed because repeating an identical pass_priority call is normal play.
TOOL_SWITCHES = {"*": False, GAME_TOOL_PREFIX + "*": True}
PERMISSIONS = {"*": "deny", GAME_TOOL_PREFIX + "*": "allow", "doom_loop": "allow"}


def executable():
    opencode = paths.settings().get("opencode_executable")
    if not opencode or not Path(opencode).is_file():
        raise RuntimeError("Run windows/Setup.ps1 with OpenCode installed (-OpenCodePath) before OpenRouter play")
    return str(opencode)


def clean_env():
    # Inherited OPENCODE_* settings could add config, credentials or plugins, so none are passed through.
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in CREDENTIAL_OVERRIDES and not key.startswith("OPENCODE_")
    }
    home = OPENCODE_HOME / "home"
    home.mkdir(parents=True, exist_ok=True)
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            **{f"XDG_{name.upper()}_HOME": str(OPENCODE_HOME / name) for name in ("config", "data", "cache", "state")},
            "OPENCODE_DISABLE_AUTOUPDATE": "1",
            "OPENCODE_DISABLE_CLAUDE_CODE": "1",
            "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1",
            "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
            "OPENCODE_DISABLE_LSP_DOWNLOAD": "1",
        }
    )
    return env


def config(mcp_url, model, tool_timeout_seconds=180):
    """Inline OpenCode config for one game; nothing from the user's own OpenCode setup is loaded."""
    result = {
        "$schema": "https://opencode.ai/config.json",
        "username": "player",
        "share": "disabled",
        "autoupdate": False,
        "snapshot": False,
        "lsp": False,
        "formatter": False,
        "plugin": [],
        "instructions": [],
        "enabled_providers": ["openrouter"],
        # A newly rotated free model may not be in OpenCode's catalog yet; this registers it either way.
        "provider": {
            "openrouter": {
                "models": {
                    model["id"]: {
                        "name": model["name"],
                        "tool_call": True,
                        "limit": {"context": model["contextLength"], "output": model["maxOutput"]},
                    }
                }
            }
        },
        "tools": TOOL_SWITCHES,
        "permission": PERMISSIONS,
        "agent": {
            "mage": {"mode": "primary", "prompt": SYSTEM_PROMPT, "tools": TOOL_SWITCHES, "permission": PERMISSIONS}
        },
    }
    if mcp_url:
        result["mcp"] = {
            "mage": {
                "type": "remote",
                "url": mcp_url,
                "enabled": True,
                "oauth": False,
                # Also the per-call limit: pass_priority waits while the human thinks.
                "timeout": tool_timeout_seconds * 1000,
            }
        }
    return result


def command(model, reasoning=DEFAULT_EFFORT):
    cmd = [executable(), "run", "--pure", "--format", "json", "--agent", "mage", "--model", "openrouter/" + model]
    if reasoning != DEFAULT_EFFORT:
        cmd.extend(["--variant", reasoning])
    return cmd


def catalog_model(model):
    models = json.loads(MODELS_PATH.read_text(encoding="utf-8")) if MODELS_PATH.is_file() else {}
    if model not in models:
        raise ValueError(f"{model} is not in the OpenRouter free catalog; reopen the launcher to refresh")
    return models[model]


def start(prompt, stdout, stderr, mcp_url=None, *, model, reasoning=DEFAULT_EFFORT, tool_timeout_seconds=180):
    env = clean_env()
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps(config(mcp_url, catalog_model(model), tool_timeout_seconds))
    proc = subprocess.Popen(
        command(model, reasoning),
        cwd=paths.PLAYER_CWD,
        env=env,
        stdin=subprocess.PIPE,
        stdout=stdout,
        stderr=stderr,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    proc.stdin.write(prompt.encode("utf-8"))
    proc.stdin.close()
    return proc


def require_game_only_events(events):
    for event in events:
        part = event.get("part") or {}
        if part.get("type") == "tool":
            name = part.get("tool", "")
            if not name.startswith(GAME_TOOL_PREFIX) and name not in HARMLESS_TOOLS:
                raise RuntimeError("Information boundary violation: the player used a non-game tool")


def usage(events):
    steps = [event["part"] for event in events if (event.get("part") or {}).get("type") == "step-finish"]
    if not steps:
        return []
    totals = {"steps": len(steps), "input": 0, "output": 0, "reasoning": 0, "cache_read": 0, "cost": 0}
    for step in steps:
        tokens = step.get("tokens", {})
        for key in ("input", "output", "reasoning"):
            totals[key] += tokens.get(key, 0)
        totals["cache_read"] += tokens.get("cache", {}).get("read", 0)
        totals["cost"] += step.get("cost", 0)
    return [totals]


def failure_reason(events):
    errors = [event for event in events if event.get("type") == "error"]
    if not errors:
        return None
    message = (errors[-1].get("error") or {}).get("data", {}).get("message") or "OpenCode reported an error"
    lowered = message.lower()
    if "per-day" in lowered:
        hint = "The daily free-model request limit is used up; it resets at midnight UTC."
    elif "rate-limit" in lowered or "rate limit" in lowered:
        hint = "Free models are often busy: choose another free model, or try again later."
    else:
        return message
    return message.rstrip(". ") + ". " + hint


def read_key():
    """The stored key, used only for openrouter.ai requests here; never returned to catalogs or logs."""
    if not AUTH_PATH.is_file():
        raise RuntimeError("Sign into OpenRouter before opening OpenRouter matches (Sign-In-OpenRouter.cmd).")
    entry = json.loads(AUTH_PATH.read_text(encoding="utf-8")).get("openrouter")
    if not entry or entry.get("type") != "api" or not entry.get("key"):
        raise RuntimeError("Sign into OpenRouter before opening OpenRouter matches (Sign-In-OpenRouter.cmd).")
    return entry["key"]


def get_json(url, key=None):
    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    # Only the fixed https://openrouter.ai URLs above are requested.
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def read_opencode_efforts():
    """Reasoning variants OpenCode knows for each OpenRouter model, from its refreshed models.dev catalog."""
    result = subprocess.run(
        [executable(), "models", "openrouter", "--verbose", "--refresh", "--pure"],
        cwd=paths.PLAYER_CWD,
        env=clean_env(),
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        timeout=120,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return parse_opencode_models(result.stdout)


def parse_opencode_models(text):
    decoder = json.JSONDecoder()
    efforts = {}
    for match in re.finditer(r"^\{", text, re.MULTILINE):
        try:
            item, _ = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and "id" in item:
            efforts[item["id"]] = list(item.get("variants") or {})
    return efforts


def is_free(item):
    pricing = item.get("pricing", {})
    try:
        if any(float(pricing.get(key) or 0) != 0 for key in ("prompt", "completion", "request")):
            return False
    except ValueError:
        return False
    return (
        "tools" in item.get("supported_parameters", [])
        and "text" in item.get("architecture", {}).get("output_modalities", ["text"])
        and item["id"] not in EXCLUDED_MODELS
    )


def read_catalog(listing, known_efforts):
    models = []
    for item in sorted(filter(is_free, listing["data"]), key=lambda entry: entry["name"].lower()):
        top = item.get("top_provider") or {}
        context = int(item.get("context_length") or top.get("context_length") or 0)
        if context <= 0:
            continue
        models.append(
            {
                "id": item["id"],
                "name": item["name"],
                "efforts": [DEFAULT_EFFORT, *known_efforts.get(item["id"], [])],
                "defaultEffort": DEFAULT_EFFORT,
                "isDefault": not models,
                "contextLength": context,
                "maxOutput": int(top.get("max_completion_tokens") or min(context, 32768)),
            }
        )
    if not models:
        raise RuntimeError("OpenRouter lists no free models with tool support right now")
    return {
        "id": PROVIDER,
        "playerType": "OpenRouter free",
        "playerName": "OpenRouter",
        "auth": "OpenRouter key in the isolated OpenCode sign-in",
        "models": models,
    }


def daily_free_requests(key):
    # Only the free-request counter is kept; credit and account fields in the response are ignored.
    counter = get_json(KEY_URL, key).get("data", {}).get("free_model_daily_requests") or {}
    return {name: counter.get(name) for name in ("used", "limit", "remaining")}


def discover():
    key = read_key()
    catalog = read_catalog(get_json(MODELS_URL), read_opencode_efforts())
    # start() runs in a separate process and needs the context limits, which the Java client never passes.
    MODELS_PATH.write_text(json.dumps({item["id"]: item for item in catalog["models"]}, indent=2), encoding="utf-8")
    try:
        catalog["freeRequestsToday"] = daily_free_requests(key)
    except OSError:
        catalog["freeRequestsToday"] = None
    return catalog


def validate_selection(catalog, model, reasoning):
    for item in catalog["models"]:
        if item["id"] == model:
            if reasoning not in item["efforts"]:
                raise ValueError(f"{model} does not support effort level {reasoning}")
            return
    raise ValueError(f"{model} is not in the OpenRouter free catalog; reopen the launcher to refresh")
