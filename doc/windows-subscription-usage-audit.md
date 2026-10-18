# ChatGPT subscription usage audit

Audited 2026-10-18 against fork commit `f1ecd8ae64cae03626b5307964be1bf153d7108f`. This is an offline analysis of one completed Commander duel, not a model-strength benchmark. No new model game was started for this audit.

There is worthwhile optimization work in the player interface. The clearest opportunity is to avoid asking the model to decline empty priority prompts one at a time. Repeated full board descriptions also grow the conversation unnecessarily. The evidence does not show runaway retries or a broken prompt cache, and it does not establish a percentage reduction in subscription allowance.

## Measured baseline

| Measurement | Result |
| --- | ---: |
| Model and reasoning | `gpt-5.6-sol`, high |
| Gameplay time | 970.765 seconds, about 16 minutes |
| Complete session including setup/cleanup | 994.750 seconds |
| Game tool calls, including errors | 98 |
| Successfully recorded gateway responses, including a JSON-RPC error | 97 |
| Cumulative input tokens reported by Codex | 9,289,513 |
| Cached input tokens | 9,108,608 (98.05% of input) |
| Input not reported as cached | 180,905 |
| Output tokens | 10,698 |
| Reported reasoning output tokens | 5,217 |
| Model thread starts / turn starts / turn completions | 1 / 1 / 1 |

These input counts accumulate across the model's requests during the game; they do not describe a single nine-million-token prompt. Reasoning output is not added to output again. The logs do not provide actual subscription allowance charges or a reliable allowance-per-token conversion. Official OpenAI documentation says model, context, complexity, reasoning, tools and caching affect usage, and that credit prices alone do not determine included subscription consumption. [OpenAI pricing and usage documentation](https://learn.chatgpt.com/docs/pricing)

## Findings, in recommended order

### 1. Empty priority prompts create avoidable model round trips

The model called `choose_action` 93 times and `pass_priority` only twice. Among the recorded single-step declines, 57 followed a `GAME_SELECT` boolean priority prompt with no listed choices. This is 57 of 98 tool calls, not proof that 58% of tokens or allowance can be saved.

The GUI prompt already recommends `pass_priority`, but that recommendation did not produce efficient behavior in this game. The native command can block locally through intervening priority windows, returning for playable non-mana actions, combat or non-priority choices. The two actual calls waited about 15 and 116 seconds, demonstrating that waiting for the human does not require busy polling by the model.

Recommended change: make efficient passing part of the tool interface/policy, with explicit tests for the native legal-action checks. Prefer the existing blocking operation when the model elects to pass an ordinary priority window. Do not indiscriminately answer every boolean prompt with no: mulligans, targeting, combat and other confirmations require decisions. Do not substitute `until=my_turn` as a universal optimization; that can skip useful responses during an opponent's turn. The current command intentionally passes the first priority window, so it must not be invoked automatically while a real action is still under consideration.

Source: `windows/gui_player.py:22`; `Mage.Client.Bridge/src/main/java/mage/client/bridge/tools/PassPriorityTool.java:11`; `Mage.Client.Bridge/src/main/java/mage/client/bridge/processor/BridgePassPriorityFlow.java:55` and `:295`.

### 2. Identical boards are repeatedly resent

Of 93 responses containing a board, 28 contained a board exactly equal to the most recently transmitted board. Board data accounted for 381,299 of 446,353 compact JSON payload bytes (85.4%). None of the recorded requests used a board/snapshot cursor.

An offline simulation replaced only identical boards with an explicit unchanged marker, keeping all other response fields. Payload size fell from 446,353 to 335,882 bytes, a 24.75% reduction. Restoring the last board reconstructed all 96 successful tool payloads exactly; the remaining JSON-RPC error was retained unchanged. This proves lossless reconstruction for this trace, not unchanged model performance or a 24.75% quota saving.

An important interface gap: `choose_action`, which generated almost all the responses, does not accept a board cursor. Other tools do. Merely telling the model to pass cursors cannot fix the dominant path. Existing cursor semantics also include action-snapshot changes, so changing or stripping cursor/game-sequence values would risk correctness.

Recommended change: add an explicit unchanged-board contract to the GUI adapter, with reliable first/full snapshots and recovery after context compaction. Keep all new action choices, sequencing, stack, combat, life, counters, zones, visibility and rules changes. Introduce static card-text references only later, keyed by the actual rules text as well as card identity so modified cards remain accurate.

Source: `Mage.Client.Bridge/src/main/java/mage/client/bridge/tools/ChooseActionTool.java:45`; `windows/game_tool_gateway.py:43`.

### 3. The MCP response has two representations of the same value

96 of the 97 recorded responses carried the same JSON value both as text content and as structured content. `McpServer.handleToolsCall` explicitly creates both, and the Windows gateway forwards both.

Keeping a single compact representation reduced simulated wire-response bytes from 960,329 to 506,260 (47.28%). Combining that with identical-board reuse reduced them to 383,637 (60.05%). **These are transport-byte measurements, not measured model-token or subscription savings.** The installed Codex client's handling of the two representations was not established; it may select one before constructing model input. This could be compatibility overhead in the transport/log only. Verify the actual client-to-model payload before treating removal as an allowance optimization.

Source: `Mage.Client.Bridge/src/main/java/mage/client/bridge/McpServer.java:225`; `windows/game_tool_gateway.py:71`.

### 4. Failed calls leave incomplete gateway telemetry

One `choose_action` call timed out at about 180 seconds. It appears in the Codex events but has no corresponding gateway response record, because transport exceptions bypass the trace-writing code. A final log query also failed after the native bridge had shut down. Neither became a restart loop in this game.

Recommended change: record every attempted call and its terminal status, including timeout and transport failure, with safe error categories. Preserve timestamps, duration and request IDs without recording credentials. Do not automatically retry a timed-out action: the action may already have been applied. This improves diagnosis and prevents duplicate actions; it is not the main demonstrated source of usage here.

Source: `windows/game_tool_gateway.py:66` through `:100`.

## What appears to be working

- Caching is active, with 98.05% of input reported cached. Cached context still participates in usage; the cache does not make a long conversation free. The precise subscription impact is account/service dependent.
- There was one model thread and one completed agent turn, without repeated process starts or conversation resets.
- The model did not repeatedly call `get_game_state` or oracle/history tools. Its calls were 93 choose-action, two get-choices, two pass-priority and one game-log query.
- The supervisor's once-per-second pregame readiness checks query the local bridge, not the model. Waiting in a tool does not itself create an inference loop.
- User configuration, unrelated project documents, other MCP servers, shell, browser and other general tools are excluded from the isolated player invocation. The game player exposes only its eight allow-listed tools.

## Validation before enabling an optimization

Keep the same model, high reasoning level, decks and legal information boundary initially. Start with deterministic fixtures and offline trace replay; there is no reason to lower intelligence settings just to test interface correctness.

1. Verify passing stops for playable instants/abilities, combat, target/amount choices, mulligans, triggers, cancellation, elimination and game end. Test both seats and a human taking longer than the tool timeout.
2. Verify unchanged-board reconstruction, initial snapshots, changed rules/state, stale cursors, per-player isolation and recovery after compaction. Never introduce the opponent's private hand or deck order.
3. Verify whether duplicate MCP forms actually reach the model. Do not infer this from the JSON event log alone.
4. After offline checks, use a short controlled live comparison at the same model/effort. Capture total/fresh/cached input, output/reasoning, calls, pass types, timeouts, wall time and observed account allowance where available. One game cannot establish strength preservation or an exact quota reduction.

No gameplay behavior, model selection or reasoning setting was changed by this investigation. Sanitized follow-up issues are recorded in the repository. Raw game traces and login data remain outside version control.
