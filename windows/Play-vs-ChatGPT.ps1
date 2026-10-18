$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$sessionFolder = Join-Path $repoRoot '.windows-local/outputs/gui-sessions'
New-Item -ItemType Directory -Force -Path $sessionFolder | Out-Null
$pythonPath = Join-Path $repoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot '.windows-local/settings.json'))) { throw 'Run windows/Setup.ps1 first.' }
$running = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.ExecutablePath -eq $pythonPath -and $_.CommandLine -and $_.CommandLine.Contains('windows.gui_session') }
if ($running) { Write-Output 'A You vs ChatGPT session is already running. Close its XMage window before opening another.'; exit 0 }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$worker = Start-Process -FilePath $pythonPath -ArgumentList @('-u', '-m', 'windows.gui_session') -WorkingDirectory $repoRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $sessionFolder "launcher-$stamp.log") -RedirectStandardError (Join-Path $sessionFolder "launcher-$stamp-errors.log") -PassThru
Write-Output "Opening XMage match configuration. No model game starts until you start the match. Session process: $($worker.Id)"
