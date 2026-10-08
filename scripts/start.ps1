# Chay may chu VietSafe cuc bo (Windows). Co the truyen them tham so: .\start.ps1 -Port 9000
param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot 'backend'

$candidatePaths = @(
    "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe",
    "$env:USERPROFILE\anaconda3\python.exe"
)
$pythonExecutable = $null
foreach ($candidate in $candidatePaths) {
    if (Test-Path -LiteralPath $candidate) { $pythonExecutable = $candidate; break }
}
if (-not $pythonExecutable) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) { $pythonExecutable = $pythonCommand.Source }
}
if (-not $pythonExecutable) {
    Write-Host 'Python 3.10+ is required. Install Python and run this file again.' -ForegroundColor Yellow
    Read-Host 'Press Enter to close'
    exit 1
}
Write-Host ''
Write-Host '  VIETSAFE - Local traffic warning map' -ForegroundColor Cyan
Write-Host "  Open http://127.0.0.1:$Port in your browser."
Write-Host '  Demo data only. Press Ctrl+C to stop.'
Write-Host ''
Set-Location -LiteralPath $backendDir
& $pythonExecutable -m vietsafe --port $Port
if ($LASTEXITCODE -ne 0) { Read-Host 'Press Enter to close' }
