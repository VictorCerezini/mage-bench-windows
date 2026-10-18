# Windows and ChatGPT/Claude/OpenRouter/Z.ai LLM support

This fork adds Windows launchers for native Mad controls, ChatGPT-subscription
and Claude-subscription players, OpenRouter free-model and Z.ai GLM Coding Plan
players, and a normal XMage GUI seat where a human can play against them. The match
configuration GUI adds local **ChatGPT subscription**, **Claude subscription**,
**OpenRouter free** and **Z.ai GLM Coding Plan** opponents, with bridge seat selection for multiplayer. The game rules, cards and Mad AI are unchanged. The engine baseline is XMage
1.4.61V1, inherited from Mage-Bench commit
`370e14523fc49b50b42e8af65557a8875490d800`.

## Setup

Install JDK 21, Maven, uv, and at least one player CLI:

- **ChatGPT**: the Codex CLI with its supported ChatGPT sign-in (`codex login`).
- **Claude**: Claude Code with its supported Claude subscription sign-in
  (`claude auth login --claudeai`, choosing your Claude Pro/Max account, not an API key).
  Double-click `windows/Sign-In-Claude.cmd` to do this with the configured CLI.
- **OpenRouter free models**: the OpenCode CLI (`npm install -g opencode-ai`) and an
  OpenRouter API key from <https://openrouter.ai/settings/keys>. Double-click
  `windows/Sign-In-OpenRouter.cmd` and paste the key; it is stored only in
  `.windows-local/opencode-home`, separate from your normal OpenCode setup.
- **Z.ai GLM Coding Plan**: the same OpenCode CLI and your Coding Plan API key from
  <https://z.ai/manage-apikey/apikey-list>. Double-click `windows/Sign-In-ZAI.cmd` and
  paste the key; it is stored next to the OpenRouter one. The plan may only be used
  within officially supported tools, and OpenCode is one of them.

Subscription limits and actual model access apply. ChatGPT and Claude need no
developer API key, and their authentication data is never copied. OpenRouter and
Z.ai keys are read only by the isolated OpenCode player.

From the repository root in PowerShell:

```powershell
& .\windows\Setup.ps1 -JavaHome $env:JAVA_HOME
```

`-MavenPath` can select a portable `mvn.cmd`. `-CodexPath` can select the native
Windows `codex.exe`; npm's standard Windows layout is also recognized.
`-ClaudePath` can select `claude.exe`; otherwise `claude.exe` on `PATH` is used,
then the copy bundled with the Claude desktop app (its versioned folder moves when
the app updates, so rerun Setup afterwards). `-OpenCodePath` can select
`opencode.exe`; npm's `opencode-ai` layout is also recognized. Setup needs at least
one of the three CLIs. `-CpuOnly` prepares native controls without requiring either. Setup builds the
Java modules and separate Java GUI/preferences helpers. `-SkipBuild` reuses an
already-built checkout and Python environment. `-MavenRepository` selects an
existing dependency cache; otherwise setup uses `.windows-local/m2`.

Machine paths, helper binaries, caches, player working directory and all new
session output stay under ignored `.windows-local/`. No global Codex config or
Nexus installation is changed. Keep the checkout at its configured location, or
rerun setup after moving it. Build/runtime Maven uses its actual launcher and raw
logs because startup monitoring and process-tree cleanup need unfiltered output.

## Play or test

Double-click `windows/Play-vs-LLM.cmd` (or the original `windows/Play-vs-ChatGPT.cmd`;
both open the same session), or run:

```powershell
& .\windows\Play-vs-ChatGPT.ps1
```

The visible window is **XMage - LLM subscription matches**. It opens the normal
**New Table** dialog. Under **Other Players**, choose **ChatGPT subscription** or
**Claude subscription**, **OpenRouter free** or **Z.ai GLM Coding Plan**, then select its **Model**,
**Reasoning**, and **Deck**.
Select your own deck in **Player 1 (You)**. Native opponent types, including Mad,
remain available, and different seats can use different providers.

Only providers whose CLI is signed in are offered; the launcher log names any
provider that was skipped and why. Sign in, then reopen the launcher.

### Claude models

Claude Code has no account model-list call, so the selector offers **Claude Opus
5.5** (default), **Claude Sonnet 5.5** and **Claude Haiku 5.5** with effort levels
low, medium (default), high, xhigh and max. Discovery only checks that Claude Code
is signed in with a Claude subscription (`claude auth status`); it starts no
inference. The selected model ID is passed verbatim and model-access fallback is
disabled, so a model your plan cannot use fails at game start instead of silently
playing as another model. Higher effort uses more of your subscription allowance.

### OpenRouter free models

OpenRouter's free models change often, so every launch asks OpenRouter for the
models that are free right now and support tool calls, and offers those. The free
router (`openrouter/free`) is left out because it switches models between requests.
Reasoning choices come from OpenCode's refreshed model catalog; **default** leaves
the effort to the model, and a model OpenCode does not know yet offers only that.
A seat saved with a model that has since left the free list falls back to the
first listed model.

OpenRouter limits free models to 20 requests a minute and 50 a day, or 1,000 a day
once the account has bought at least $10 of credits. Each game tool call is a
request, so a full game (roughly 70 to 80 calls) does not fit in 50. The launcher
log shows today's count. Free models may also require allowing free endpoints in
your OpenRouter privacy settings; check each model's data policy there.

### Z.ai GLM Coding Plan models

The selector offers **GLM-5.3** (default) and **GLM-5.3-Flash**, the models Z.ai
documents for every plan tier. Z.ai's model list is account-wide rather than per
plan, and the plan silently routes older IDs (GLM-5.2 and GLM-5.1 to GLM-5.3,
GLM-4.7 to GLM-5.3-Flash), so those are left out to keep the seat playing as the
model it shows. Discovery lists the plan endpoint's models to confirm the key works;
that is not inference and uses no allowance. Effort levels come from OpenCode's
catalog; **default** leaves the effort to the model. Games count against the plan's
5-hour and weekly allowances, and Z.ai recommends one concurrent session on Lite.

### ChatGPT models

The launcher asks the installed Codex CLI for the models available to its current
ChatGPT sign-in. Reasoning choices change with the selected model. No model IDs
or supported effort levels are invented, and an unavailable selection fails
explicitly. Model discovery uses `account/read` and `model/list` only: it starts
no thread or inference. See the [official model discovery documentation](https://learn.chatgpt.com/docs/app-server#list-models-modellist).

The selector is limited to **GPT-6 Astra**, **GPT-6 Luna**, and **GPT-6.1 Sol**, and
only shows those returned by the current sign-in. GPT-5.6 models and GPT-6 Sol are
excluded. Reopen the launcher to refresh the menu after changing this policy.

The connector version matters: on 18 October 2026 the installed 0.153.4 CLI
returned Astra plus the older 5.6 models even after refreshing its catalog.
An isolated 0.163.0 copy returned all three requested GPT-6 models through the
same sign-in. Discovery and configuration rendering were verified without model
turns; account/client availability is still determined by the live catalog.

To reproduce this project-local connector installation from the repository root:

```powershell
npm install --prefix .windows-local/tools/codex-0.163.0 --no-audit --no-fund @openai/codex@0.163.0
$connector = (Resolve-Path '.windows-local/tools/codex-0.163.0/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe').Path
$runtime = Get-Content -LiteralPath '.windows-local/settings.json' -Raw | ConvertFrom-Json
& .\windows\Setup.ps1 -SkipBuild -JavaHome $runtime.java_home -MavenPath $runtime.maven_path -MavenRepository $runtime.maven_repository -CodexPath $connector
```

Close the fork before rerunning Setup. Explicit `-CodexPath` avoids npm package
layout assumptions. This keeps the global CLI in place and uses its normal
supported sign-in without copying authentication. For this PC, only the ignored
runtime `codex_executable` setting was switched, with an ignored pre-update settings
backup; Java did not need rebuilding. The existing desktop shortcut is unchanged.
Already-open clients retain their original catalog until reopened.
The read-only catalog refresh and prompt renderer are documented in the
[official CLI reference](https://learn.chatgpt.com/docs/cli/reference#codex-debug-models).

Click **Create**, wait for **ChatGPT 2** (or **Claude 2**) to join, then click **Start**. Opening the
GUI or creating a table does not consume model inference; the player starts only
when the game begins. Choose a starting player, respond to the mulligan prompt,
and play normally. Canceling/leaving the table stops its subscription worker;
closing the window stops the local session. The GUI stays open after a game.
Settings saved with the dialog include the selected model and reasoning, but
Java preferences are process-local and do not survive closing the client.

The subscription integration allows the game modes offered by **New Table**,
including **Commander Two Player Duel** and **Commander Free For All**, with the
mode's normal player count and deck-format checks. Every model seat has its own
model, reasoning, deck and bridge; a bridge waits for its configured seat instead
of racing to take any empty human seat. Canceling the table stops every model
seat. In multiplayer, a player stops after its own confirmed elimination even
if other participants are still playing. Opponent hands remain hidden.

Two lifecycle restrictions remain: **Wins must be 1**, because the subscription
supervisor does not yet handle sideboarding and later games of a match; and the
**table password must be empty**, because the bridge does not yet send one. The
error messages identify these separately. These are not restrictions on Commander
or other game formats. Tournament/draft workflows are separate from New Table
and have not been integrated with the subscription player.

The launcher defaults to no player clock, has a two-hour gameplay wall bound and
a 2,000-call bound per model, and expires an unstarted table after ten minutes.
Subscription usage limits still apply. A second launcher invocation detects the
running session. Restart an already-open client after updating the build.

Both deck fields start with 20 Island and 20 Slither Blade, an artificial 40-card
Limited deck. Use the deck buttons to choose other files and select their correct
deck format. The LLM gets no claim about the opponent's deck or starting order.
The GUI server explicitly enables normal deck validation, including Commander
deck construction rules; it does not use the developer build's permissive test
mode. The artificial Limited starter deck remains valid for its chosen format.
Card art is optional and is not included in Git. This menu is in the isolated
fork; the separately installed Nexus client is unchanged.

Run an LLM versus native Mad pilot and its complementary seat/start-order game:

```powershell
& .\windows\Run-Pilot.ps1
& .\windows\Run-Pilot.ps1 -ChoosingPlayer Mad -SwapSeats
```

These use a 15-minute clock per player, 20-minute gameplay wall bound, normal
unseeded shuffling and the same short deck. The model requested is `gpt-6-astra`
at medium reasoning. No dated model snapshot is guaranteed by that alias.
The pilot runner drives the ChatGPT player only; Claude is available in the GUI.

For a CPU-only control, which invokes no model:

```powershell
& .\.venv\Scripts\python.exe -m windows.local_smoke --games 1 --deck windows/decks/mirror-slither.dck
```

The stock orchestrator's Windows portability is not claimed: it assumes Unix
locking and launcher behavior. These launchers start the native Java modules
directly. Very fast CPU games can finish before the observer attaches; such a
missing observer completion is a harness failure, not a valid reported win.

## Efficient subscription play

GUI matches use the `gui-efficient-v1` tool policy. Your selected model and
reasoning stay unchanged. When the model submits `choice=no` alone at an observed
empty ordinary priority prompt, the gateway sends native `pass_priority` without
an `until` target. This waits through empty windows and returns for playable
actions, combat and other decisions. Mulligans, targets, amounts, mana choices,
combat selections and prompts with listed actions are not rerouted. Nothing is
automatically conceded, and failed actions are never automatically retried.

Exact repeated boards are replaced by `board_unchanged` and a `board_reference` to
the previous full board. Changes to rules, life, counters, zones or any other board
field cause a full board to be sent; new choices, stack, combat and sequence fields
are always retained. `get_action_choices` requests a full snapshot, ignoring the
native board cursor, so the model can recover after context compaction. If no
board is currently available, the next available board is full. Caches belong to
one gateway/player. Both MCP output representations remain synchronized.

Native and Codex tool waits extend slightly beyond the existing two-hour gameplay
bound (7,230 and 7,260 seconds), so a human thinking for three minutes does not
cause a tool timeout. The supervisor still checks table cancellation/window
closure every half second and stops its owned processes. Codex supports a per-MCP
tool timeout in its [official configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
The non-GUI pilot retains its native policy and 180-second tool timeout. No harness
epoch changes: native tools, rules and the stock benchmark's decisions are unchanged;
GUI policy versions are recorded separately for comparisons.

Player traces now include the requested/effective tool, request ID, terminal
outcome, latency, upstream response and, when changed, the model-facing response.
Timeouts/transport failures are recorded without exception text or automatic
mutation retries. Invalid native data stops the supervisor rather than allowing a
model recovery loop. The manifest records batched-pass attempts, boards omitted,
failed calls and response-byte totals. Bytes are not subscription-charge metrics.

On the saved Commander trace, the actual codec reconstructed all 96 successful
payloads exactly, omitted 28 identical boards, and reduced compact response bytes
from 960,329 to 725,597 (24.44%). Passing candidates numbered 57, but this fixed-call
replay does not predict how many native decisions a future blocking pass will skip.
No model calls were made for that replay. Strategic quality and allowance savings
remain to be measured in live games. See the [baseline audit](../doc/windows-subscription-usage-audit.md).

Open a fresh GUI game to use the updated worker; no Java rebuild is needed for
these adapter changes. Close/reopen the fork via its existing shortcut if unsure.

## Privacy and information boundaries

The source contains no login cache, cookies, refresh/access tokens or API keys.
Never add those files. `.windows-local`, `.codex`, authentication JSON files,
environment files and session logs are ignored. The CLI uses the user's normal
supported sign-in cache in place; the launcher never opens, copies or exports it.
Each player invocation forces ChatGPT login and removes provider credential
overrides from the child environment.

OpenRouter and Z.ai players run `opencode run` from an isolated home under
`.windows-local/opencode-home`: its `HOME`, `USERPROFILE` and XDG folders point
there, so OpenCode never reads your user profile, your normal OpenCode config or
sign-ins, skills, or CLAUDE.md. The configuration is passed inline: every built-in
OpenCode tool is switched off, every permission except the `mage_*` game tools is
denied, only the seat's provider is enabled, and plugins, instructions, sharing
and snapshots are off. Each key is sent only to its own provider (openrouter.ai or
api.z.ai) and is never written to catalogs or logs. The
supervisor stops the game if the trace shows any non-game tool.

Claude players run `claude -p` with the subscription sign-in Claude Code already
stores; the launcher reads only the `loggedIn`, `authMethod` and `apiProvider`
fields of `claude auth status` and never saves the email or organization it also
reports. API-key, auth-token, OAuth-token, Bedrock/Vertex/Foundry and base-URL
overrides are removed from the child environment, and `--bare` (API-key-only) is
never used. Every built-in tool is disabled (`--tools ""`), only the eight
`mcp__mage__*` game tools are allowed (`--strict-mcp-config`, `dontAsk`
permissions), and user/project/local settings, hooks, plugins, slash commands,
CLAUDE.md files, auto-memory and session transcripts are off. The supervisor also
stops the game if the CLI is offered or uses any non-game tool.

Only eight game tools are exposed through an allow-listed loopback gateway.
Shell, browser, plugin/app and multi-agent tools are disabled; project
instructions are omitted and the player working directory is empty. Java
Preferences use a process-local factory, preventing shared registry preference
writes. The factory also disables a redundant raw callback dump while retaining
the main observer/server JSONL logs.

Observer/server logs can contain privileged hands. They stay in ignored local
session folders and are not supplied to the LLM. Do not publish them without
review. This is a tool boundary, not a VM or separate Windows account. Native
Mad's hidden-information policy still needs a deeper audit for strength studies.
The Codex player loop differs from the stock Mage-Bench API pilot.

Completed pilot traces confirmed normal game endings and preserved token/time
metrics; a tiny artificial-deck pilot does not establish model strength. Failed
turns may not report complete usage. Subscription allowance is consumed, and a
dollar-equivalent subscription cost is unavailable. No inference or credentials
are required for the tests below.

## Tests and removal

On Windows, run the adapter tests independently of the stock Unix orchestration
fixtures:

```powershell
& .\.venv\Scripts\python.exe -m pytest --confcutdir=tests/windows tests/windows -n 0
```

They exercise HTTP filtering, accurate annotations, blocked-tool/call-budget
enforcement, unaltered baseline responses, efficient GUI priority passing and
lossless board references/recovery, credential-environment isolation,
subscription-only command configuration for both CLIs, Claude sign-in and
tool-boundary checks, OpenRouter free-model filtering, the Z.ai documented-model
list, key privacy and OpenCode isolation, multi-provider discovery, model catalog pagination/privacy,
model-specific reasoning validation, GUI player startup/cancellation/failure
cleanup with fake processes, and concurrently appended JSONL traces.
Setup also runs a Java preferences check. The upstream Python suite remains
available through `make test` on its supported environment.

Java regressions for mode validation, multiplayer seat assignment and cancellation:

```powershell
mvn -B -pl Mage.Client,Mage.Client.Bridge -Dtest=SubscriptionMatchRulesTest,SubscriptionPlayerRegistryTest,SubscriptionSupportTest,BridgeSeatSelectionTest -Dsurefire.failIfNoSpecifiedTests=false test
```

Native checks on 18 October 2026 reached the first turn of a Commander duel and
four-player Commander with a repository preconstructed deck, normal deck validation,
scripted pregame responses, confirmed commander state and hidden opponent hands.
They made zero model requests and cleaned up their processes. These checks verify
the connection and pregame interface, not strategic playing strength or every
card/game-mode combination. The bridge's full 111-test Java suite also passed.

Close the player window and stop any active runner before deleting the checkout
or `.windows-local`. Retain the user's existing Codex authentication and Nexus
installation. Existing shared Java, Maven, Python and Codex installations are
not owned by this fork.
