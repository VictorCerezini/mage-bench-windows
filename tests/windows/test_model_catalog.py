"""Account-safe discovery and model-specific reasoning validation; no inference."""

import json

import pytest

from windows.model_catalog import read_catalog, validate_selection


def model(name, efforts, *, hidden=False):
    return {
        "model": name,
        "displayName": name,
        "hidden": hidden,
        "supportedReasoningEfforts": [{"reasoningEffort": effort} for effort in efforts],
        "defaultReasoningEffort": efforts[0],
        "isDefault": True,
    }


def test_catalog_paginates_and_excludes_identity_and_hidden_models():
    calls = []

    def call(method, params):
        calls.append((method, params))
        if method == "account/read":
            return {"account": {"type": "chatgpt", "email": "private@example.invalid", "planType": "private-plan"}}
        if params["cursor"] is None:
            return {"data": [model("first", ["low", "high"])], "nextCursor": "second-page"}
        return {"data": [model("second", ["medium"]), model("hidden", ["low"], hidden=True)], "nextCursor": None}

    catalog = read_catalog(call)
    assert [item["id"] for item in catalog["models"]] == ["first", "second"]
    assert catalog["models"][0]["efforts"] == ["low", "high"]
    assert "private" not in json.dumps(catalog)
    assert [method for method, _ in calls] == ["account/read", "model/list", "model/list"]


@pytest.mark.parametrize("account", [None, {"type": "apiKey"}, {"type": "amazonBedrock"}])
def test_catalog_rejects_other_authentication_modes(account):
    with pytest.raises(RuntimeError, match="Sign into Codex with ChatGPT"):
        read_catalog(lambda *_: {"account": account})


@pytest.mark.parametrize("selection", [("missing", "low"), ("first", "ultra")])
def test_unavailable_model_or_effort_is_rejected(selection):
    with pytest.raises(ValueError, match=r"not in the available|does not support"):
        validate_selection({"models": [{"id": "first", "efforts": ["low", "high"]}]}, *selection)


def test_valid_model_specific_effort_is_accepted():
    validate_selection({"models": [{"id": "first", "efforts": ["low", "high"]}]}, "first", "high")
