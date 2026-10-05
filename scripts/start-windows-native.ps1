param(
    [int]$Port = 8026,
    [string]$Config = '',
    [switch]$Preflight
)
$ErrorActionPreference = 'Stop'
$taskRepo = Split-Path -Parent $PSScriptRoot
$taskPython = 'C:\NPD-Video-Factory\runtime\venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython -PathType Leaf)) {
    throw 'MVP1 Python runtime unavailable.'
}
$taskArguments = @('-m', 'services.windows_native.server', '--port', "$Port")
if ($Config) { $taskArguments += @('--config', (Resolve-Path -LiteralPath $Config).Path) }
if ($Preflight) { $taskArguments += '--preflight' }
Push-Location -LiteralPath $taskRepo
try { & $taskPython @taskArguments; exit $LASTEXITCODE } finally { Pop-Location }
