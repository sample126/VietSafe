param(
    [Parameter(Mandatory=$true)][string]$ResearchRoot,
    [string]$Python = "python",
    [int]$Port = 8790
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$env:VIETSAFE_AI_RESEARCH_ROOT = (Resolve-Path -LiteralPath $ResearchRoot).Path
$env:OMP_NUM_THREADS = "2"
$env:MKL_NUM_THREADS = "2"
$env:OPENBLAS_NUM_THREADS = "2"
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = Join-Path $repo "backend"
Write-Host "VietSafe: http://127.0.0.1:$Port/ (open Du bao > AI nghien cuu)"
Write-Host "Historical research replay. No training or public alerts."
Push-Location $repo
try {
    & $Python -m vietsafe --host 127.0.0.1 --port $Port
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
