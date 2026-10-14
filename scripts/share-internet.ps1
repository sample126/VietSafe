# Tao link truy cap qua Internet cho ban demo. Can cloudflared.exe dat o thu muc goc cua repo
# (neu khong co se dung du phong npx localtunnel).
param([int]$Port = 8765)
$ErrorActionPreference = 'Continue'
$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot 'backend'

Write-Host ""
Write-Host " ========================================================" -ForegroundColor Cyan
Write-Host "   VIETSAFE - TAO LINK TRUY CAP QUA INTERNET (CLOUDFLARE) " -ForegroundColor Yellow
Write-Host " ========================================================" -ForegroundColor Cyan
Write-Host ""

# Kiem tra may chu VietSafe co dang chay khong
$serverRunning = $false
try {
    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
    if ($resp.StatusCode -eq 200) { $serverRunning = $true }
} catch {}

if (-not $serverRunning) {
    Write-Host " [*] May chu VietSafe chua duoc bat. Dang tu dong khoi dong may chu..." -ForegroundColor Green
    $candidatePaths = @(
        "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe",
        "$env:USERPROFILE\anaconda3\python.exe"
    )
    $pythonExec = $null
    foreach ($candidate in $candidatePaths) {
        if (Test-Path -LiteralPath $candidate) { $pythonExec = $candidate; break }
    }
    if (-not $pythonExec) {
        $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCmd) { $pythonExec = $pythonCmd.Source }
    }
    if ($pythonExec) {
        Start-Process -FilePath $pythonExec -ArgumentList "-m vietsafe --port $Port" -WorkingDirectory $backendDir -WindowStyle Minimized
        Start-Sleep -Seconds 2
    }
}

Write-Host " [*] Dang ket noi Cloudflare Tunnel..." -ForegroundColor Green
Write-Host " [*] Link truy cap truc tiep (HTTPS) se xuat hien ngay ben duoi:" -ForegroundColor White
Write-Host " [*] Ban chi can COPY LINK va gui cho moi nguoi xem tren dien thoai/may tinh!" -ForegroundColor Yellow
Write-Host ""

$cloudflaredPath = Join-Path $repoRoot "cloudflared.exe"
if (Test-Path -LiteralPath $cloudflaredPath) {
    & $cloudflaredPath tunnel --url "http://127.0.0.1:$Port"
} else {
    Write-Host "Khong tim thay cloudflared.exe. Dang dung du phong qua npx localtunnel..." -ForegroundColor Yellow
    npx localtunnel --port $Port
}

Read-Host "Nhan Enter de thoat"
