$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$localRoot = Join-Path $repoRoot '.windows-local'
$settingsPath = Join-Path $localRoot 'settings.json'
if (-not (Test-Path -LiteralPath $settingsPath)) { throw 'Run windows/Setup.ps1 first.' }
$opencode = (Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json).opencode_executable
if (-not $opencode -or -not (Test-Path -LiteralPath $opencode)) { throw 'No OpenCode executable is configured. Rerun windows/Setup.ps1 (optionally with -OpenCodePath).' }

# OpenRouter models play through OpenCode, which keeps this sign-in under the git-ignored .windows-local
# folder. Your normal OpenCode setup, and the Claude and ChatGPT sign-ins, are never read or changed.
$home_ = Join-Path $localRoot 'opencode-home'
foreach ($name in 'config', 'data', 'cache', 'state') {
    $folder = Join-Path $home_ $name
    New-Item -ItemType Directory -Force -Path $folder | Out-Null
    Set-Item "Env:XDG_$($name.ToUpper())_HOME" $folder
}
foreach ($name in 'OPENCODE_API_KEY', 'OPENCODE_AUTH_CONTENT', 'OPENCODE_CONSOLE_TOKEN', 'OPENCODE_CONFIG', 'OPENCODE_CONFIG_CONTENT', 'OPENCODE_CONFIG_DIR') {
    Remove-Item "Env:$name" -ErrorAction SilentlyContinue
}
$env:OPENCODE_DISABLE_AUTOUPDATE = '1'
$authPath = Join-Path $home_ 'data/opencode/auth.json'

function Test-OpenRouterSignIn {
    # Only provider names are read; the stored key is never printed.
    if (-not (Test-Path -LiteralPath $authPath)) { return $false }
    $names = (Get-Content -LiteralPath $authPath -Raw | ConvertFrom-Json).PSObject.Properties.Name
    return $names -contains 'openrouter'
}

if (Test-OpenRouterSignIn) {
    Write-Output 'XMage is already signed into OpenRouter. Open Play-vs-LLM.cmd to play.'
    exit 0
}
Write-Output 'Create an API key at https://openrouter.ai/settings/keys, then paste it when asked below.'
Write-Output 'The key is stored only in this repository''s git-ignored .windows-local folder.'
& $opencode auth login --provider openrouter
if (Test-OpenRouterSignIn) {
    Write-Output 'Signed into OpenRouter. Close any open XMage window, then open Play-vs-LLM.cmd.'
    exit 0
}
throw 'OpenRouter sign-in did not complete.'
