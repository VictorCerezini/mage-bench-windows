"""Subscription CLIs that can drive a GUI seat; each keeps authentication inside its own CLI."""

from collections.abc import Callable
from dataclasses import dataclass

from windows import claude_client, model_catalog, subscription_client


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    auth: str
    events_file: str
    stderr_file: str
    discover: Callable
    validate_selection: Callable
    start: Callable
    require_game_only_events: Callable
    usage: Callable


def codex_usage(events):
    return [event["usage"] for event in events if event.get("type") == "turn.completed"]


def codex_game_only_events(events):
    for event in events:
        if event.get("type") == "item.completed" and event["item"].get("type") in {
            "command_execution",
            "file_change",
            "web_search",
        }:
            raise RuntimeError("Information boundary violation: the player used a non-game tool")


PROVIDERS = {
    item.id: item
    for item in (
        Provider(
            id="chatgpt_subscription",
            label="ChatGPT",
            auth="existing Codex ChatGPT login",
            events_file="codex-events.jsonl",
            stderr_file="codex-stderr.log",
            discover=model_catalog.discover,
            validate_selection=model_catalog.validate_selection,
            start=subscription_client.start,
            require_game_only_events=codex_game_only_events,
            usage=codex_usage,
        ),
        Provider(
            id=claude_client.PROVIDER,
            label="Claude",
            auth="existing Claude Code subscription login",
            events_file="claude-events.jsonl",
            stderr_file="claude-stderr.log",
            discover=claude_client.discover,
            validate_selection=claude_client.validate_selection,
            start=claude_client.start,
            require_game_only_events=claude_client.require_game_only_events,
            usage=claude_client.usage,
        ),
    )
}


def get(provider_id):
    if provider_id not in PROVIDERS:
        raise ValueError(f"Unknown subscription provider: {provider_id}")
    return PROVIDERS[provider_id]


def discover_all(providers=None):
    """Return every signed-in provider's catalog; one missing sign-in does not block the others."""
    available, unavailable = [], []
    for provider in (providers or PROVIDERS).values():
        try:
            available.append(provider.discover())
        except Exception as error:  # noqa: BLE001 - reported to the launcher log, never fatal per provider
            unavailable.append({"id": provider.id, "reason": str(error)})
    if not available:
        raise RuntimeError("No subscription player is available: " + "; ".join(item["reason"] for item in unavailable))
    return {"providers": available, "unavailable": unavailable}


def catalog_entry(catalog, provider_id):
    for entry in catalog["providers"]:
        if entry["id"] == provider_id:
            return entry
    raise ValueError(f"{provider_id} is not signed in for this session; reopen the launcher after signing in")
