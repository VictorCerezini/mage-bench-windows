"""GUI-only passing policy and lossless references to unchanged player boards."""

import copy
import json

ACTION_TOOLS = {"choose_action", "get_action_choices", "pass_priority"}


class PlayerView:
    def __init__(self):
        self.last_action = None
        self.board = None
        self.board_reference = 0
        self.full_board_required = True
        self.batched_pass_attempts = 0
        self.omitted_boards = 0

    def invalidate_action(self):
        self.last_action = None

    def prepare_request(self, request):
        effective = copy.deepcopy(request)
        params = effective["params"]
        tool = params["name"]
        arguments = params.setdefault("arguments", {})
        if tool in {"get_action_choices", "get_game_state"}:
            self.full_board_required = True
        if tool in ACTION_TOOLS:
            # Own this cache completely: native cursors also track action snapshots.
            arguments.pop("board_cursor", None)
        if tool == "choose_action" and self.is_empty_priority_pass(arguments):
            params["name"] = "pass_priority"
            params["arguments"] = {}
            self.batched_pass_attempts += 1
        return effective

    def is_empty_priority_pass(self, arguments):
        if set(arguments) != {"choice"} or not isinstance(arguments["choice"], str):
            return False
        if arguments["choice"].strip().lower() not in {"no", "false"}:
            return False
        action = self.last_action
        return (
            action is not None
            and action.get("action_pending") is True
            and action.get("action_type") == "GAME_SELECT"
            and action.get("response_type") == "boolean"
            and not action.get("choices")
            and not action.get("combat_phase")
            and not any(action.get(key) for key in ("error", "error_code", "game_over", "player_dead"))
        )

    def model_response(self, tool, response):
        if "error" in response or response["result"].get("isError"):
            self.invalidate_action()
            return response
        if tool == "concede":
            self.invalidate_action()
        if tool not in ACTION_TOOLS:
            return response
        result = response["result"]
        texts = [part for part in result["content"] if part["type"] == "text"]
        if len(texts) != 1:
            raise ValueError("Expected one JSON player-view text result")
        payload = json.loads(texts[0]["text"])
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON player-view object")
        if "structuredContent" in result and result["structuredContent"] != payload:
            raise ValueError("Player-view text and structured content disagree")
        self.last_action = copy.deepcopy(payload)
        if "board" not in payload:
            return response
        reduced = copy.deepcopy(payload)
        if payload["board"] == self.board:
            if not self.full_board_required and "board_unchanged" not in payload:
                reduced.pop("board")
                reduced["board_unchanged"] = True
                self.omitted_boards += 1
        else:
            self.board = copy.deepcopy(payload["board"])
            self.board_reference += 1
        reduced["board_reference"] = self.board_reference
        self.full_board_required = False
        outgoing = copy.deepcopy(response)
        for part in outgoing["result"]["content"]:
            if part["type"] == "text":
                part["text"] = json.dumps(reduced, separators=(",", ":"), ensure_ascii=False)
        if "structuredContent" in outgoing["result"]:
            outgoing["result"]["structuredContent"] = reduced
        return outgoing

    @staticmethod
    def describe_tool(tool):
        name = tool["name"]
        if name not in ACTION_TOOLS:
            return
        if name == "choose_action":
            extra = (
                " In this GUI, choice=no alone at an observed empty ordinary priority prompt uses pass_priority "
                "to wait for the next decision. It does not answer combat, mulligan or targeting choices."
            )
        elif name == "get_action_choices":
            extra = " Always returns the full board when available, even with board_cursor; use to recover context."
        else:
            extra = " Omit until to stop at the next playable action, combat or other decision."
        tool["description"] = (
            tool["description"]
            + extra
            + (
                " Identical boards may be replaced by board_unchanged=true and board_reference pointing to the "
                "previous full board. All other fields are current. If that board is no longer in your context, "
                "call get_action_choices for a full board. Native board_cursor is ignored by this GUI adapter."
            )
        )
        if "outputSchema" in tool:
            tool["outputSchema"]["properties"]["board_reference"] = {
                "type": "integer",
                "description": "GUI reference to the last full identical board",
            }
