$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
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
Write-Host '  Open http://127.0.0.1:8765 in your browser.'
Write-Host '  Demo data only. Press Ctrl+C to stop.'
Write-Host ''
& $pythonExecutable (Join-Path $PSScriptRoot 'server.py') --port 8765
if ($LASTEXITCODE -ne 0) { Read-Host 'Press Enter to close' }
