param([int]$TimeoutSeconds = 1200, [ValidateSet('Astra','Mad')][string]$ChoosingPlayer = 'Astra', [switch]$SwapSeats)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$arguments = @('-u', '-m', 'windows.subscription_runner', '--timeout', $TimeoutSeconds, '--choosing-player', $ChoosingPlayer)
if ($SwapSeats) { $arguments += '--swap-seats' }
Push-Location $repoRoot
try { & (Join-Path $repoRoot '.venv/Scripts/python.exe') @arguments; $result = $LASTEXITCODE } finally { Pop-Location }
exit $result
