"""Verify subscription isolation with fake settings and no model invocation."""

import json
import os

from windows import paths, subscription_client


def test_subscription_command_forces_chatgpt_and_restricts_tools(monkeypatch):
    monkeypatch.setattr(paths, "settings", lambda: {"codex_executable": "C:/Tools/codex.exe"})
    command = subscription_client.command("http://127.0.0.1:12345/mcp")
    configs = {
        command[index + 1].split("=", 1)[0]: json.loads(command[index + 1].split("=", 1)[1])
        for index, value in enumerate(command)
        if value == "-c"
    }
    assert configs["forced_login_method"] == "chatgpt"
    assert configs["model_provider"] == "openai"
    assert configs["features.shell_tool"] is False
    assert configs["features.browser_use"] is False
    assert configs["features.apps"] is False
    assert configs["features.multi_agent"] is False
    assert configs["project_doc_max_bytes"] == 0
    assert configs["mcp_servers.mage.enabled_tools"] == subscription_client.TOOLS
    assert "--ignore-user-config" in command
    assert "--ephemeral" in command


def test_provider_credentials_are_removed_only_from_child_environment(monkeypatch):
    names = [
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "CODEX_ACCESS_TOKEN",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENROUTER_API_KEY",
        "OPENAI_BASE_URL",
    ]
    for name in names:
        monkeypatch.setenv(name, "test-value-not-a-secret")
    cleaned = subscription_client.clean_env()
    assert all(name not in cleaned for name in names)
    assert all(os.environ[name] == "test-value-not-a-secret" for name in names)
