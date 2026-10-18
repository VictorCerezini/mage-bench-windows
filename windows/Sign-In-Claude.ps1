$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$settingsPath = Join-Path $repoRoot '.windows-local/settings.json'
if (-not (Test-Path -LiteralPath $settingsPath)) { throw 'Run windows/Setup.ps1 first.' }
$claude = (Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json).claude_executable
if (-not $claude -or -not (Test-Path -LiteralPath $claude)) { throw 'No Claude Code executable is configured. Rerun windows/Setup.ps1 (optionally with -ClaudePath).' }
# Credential overrides would make Claude Code ignore the subscription sign-in, as they would during play.
foreach ($name in 'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN') { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }

function Get-ClaudeAuth {
    # Only these fields are shown; the email and organization in the status are never printed or saved.
    $status = & $claude auth status --json 2>$null | ConvertFrom-Json
    [pscustomobject]@{ loggedIn = $status.loggedIn; authMethod = $status.authMethod }
}

$auth = Get-ClaudeAuth
if ($auth.loggedIn -and $auth.authMethod -eq 'claude.ai') {
    Write-Output 'Claude Code is already signed in with your Claude subscription. Open Play-vs-ChatGPT.cmd to play.'
    exit 0
}
if ($auth.loggedIn) {
    Write-Output "Claude Code is signed in with '$($auth.authMethod)', not a Claude subscription. Signing that out first."
    & $claude auth logout
}
Write-Output 'A browser window will open. Sign in with the Claude account that has your Pro or Max subscription.'
& $claude auth login --claudeai
$auth = Get-ClaudeAuth
if ($auth.loggedIn -and $auth.authMethod -eq 'claude.ai') {
    Write-Output 'Signed in with your Claude subscription. Close any open XMage window, then open Play-vs-ChatGPT.cmd.'
    exit 0
}
throw "Sign-in did not complete with a Claude subscription (current method: $($auth.authMethod))."
