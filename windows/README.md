# Windows and ChatGPT subscription support

This fork adds Windows launchers for native Mad controls, a ChatGPT-subscription
player, and a normal XMage GUI seat where a human can play against that player.
The match configuration GUI adds a local ChatGPT subscription opponent, with bridge
seat selection for multiplayer. The game rules, cards and Mad AI are unchanged. The engine baseline is XMage
1.4.61V1, inherited from Mage-Bench commit
`370e14523fc49b50b42e8af65557a8875490d800`.

## Setup

Install JDK 21, Maven, uv, and the Codex CLI. Use the CLI's supported ChatGPT
sign-in (`codex login`); subscription limits and actual model access apply.
This does not require a developer API key and does not copy authentication data.

From the repository root in PowerShell:

```powershell
& .\windows\Setup.ps1 -JavaHome $env:JAVA_HOME
```

`-MavenPath` can select a portable `mvn.cmd`. `-CodexPath` can select the native
Windows `codex.exe`; npm's standard Windows layout is also recognized.
`-CpuOnly` prepares native controls without requiring Codex. Setup builds the
Java modules and separate Java GUI/preferences helpers. `-SkipBuild` reuses an
already-built checkout and Python environment. `-MavenRepository` selects an
existing dependency cache; otherwise setup uses `.windows-local/m2`.

Machine paths, helper binaries, caches, player working directory and all new
session output stay under ignored `.windows-local/`. No global Codex config or
Nexus installation is changed. Keep the checkout at its configured location, or
rerun setup after moving it. Build/runtime Maven uses its actual launcher and raw
logs because startup monitoring and process-tree cleanup need unfiltered output.

## Play or test

Double-click `windows/Play-vs-ChatGPT.cmd`, or run:

```powershell
& .\windows\Play-vs-ChatGPT.ps1
```

The visible window is **XMage - ChatGPT subscription matches**. It opens the normal
**New Table** dialog. Under **Other Players**, choose **ChatGPT subscription**,
then select its **Model**, **Reasoning**, and **Deck**. Select your own deck in
**Player 1 (You)**. Native opponent types, including Mad, remain available.

The launcher asks the installed Codex CLI for the models available to its current
ChatGPT sign-in. Reasoning choices change with the selected model. No model IDs
or supported effort levels are invented, and an unavailable selection fails
explicitly. Model discovery uses `account/read` and `model/list` only: it starts
no thread or inference. See the [official model discovery documentation](https://learn.chatgpt.com/docs/app-server#list-models-modellist).

Click **Create**, wait for **ChatGPT 2** to join, then click **Start**. Opening the
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

For a CPU-only control, which invokes no model:

```powershell
& .\.venv\Scripts\python.exe -m windows.local_smoke --games 1 --deck windows/decks/mirror-slither.dck
```

The stock orchestrator's Windows portability is not claimed: it assumes Unix
locking and launcher behavior. These launchers start the native Java modules
directly. Very fast CPU games can finish before the observer attaches; such a
missing observer completion is a harness failure, not a valid reported win.

## Privacy and information boundaries

The source contains no login cache, cookies, refresh/access tokens or API keys.
Never add those files. `.windows-local`, `.codex`, authentication JSON files,
environment files and session logs are ignored. The CLI uses the user's normal
supported sign-in cache in place; the launcher never opens, copies or exports it.
Each player invocation forces ChatGPT login and removes provider credential
overrides from the child environment.

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
enforcement, unaltered allowed responses, credential-environment isolation,
subscription-only command configuration, model catalog pagination/privacy,
model-specific reasoning validation, GUI player startup/cancellation/failure
cleanup with fake processes, and concurrently appended JSONL traces.
Setup also runs a Java preferences check. The upstream Python suite remains
available through `make test` on its supported environment.

Java regressions for mode validation, multiplayer seat assignment and cancellation:

```powershell
mvn -B -pl Mage.Client,Mage.Client.Bridge -Dtest=SubscriptionMatchRulesTest,SubscriptionPlayerRegistryTest,BridgeSeatSelectionTest -Dsurefire.failIfNoSpecifiedTests=false test
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
