$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath $PSScriptRoot

Write-Host ""
Write-Host " ========================================================" -ForegroundColor Cyan
Write-Host "   VIETSAFE - TAO LINK TRUY CAP QUA INTERNET (CLOUDFLARE) " -ForegroundColor Yellow
Write-Host " ========================================================" -ForegroundColor Cyan
Write-Host ""

# Kiem tra may chu VietSafe co dang chay khong
$serverRunning = $false
try {
    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8765/api/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
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
        Start-Process -FilePath $pythonExec -ArgumentList "server.py --port 8765" -WorkingDirectory $PSScriptRoot -WindowStyle Minimized
        Start-Sleep -Seconds 2
    }
}

Write-Host " [*] Dang ket noi Cloudflare Tunnel..." -ForegroundColor Green
Write-Host " [*] Link truy cap truc tiep (HTTPS) se xuat hien ngay ben duoi:" -ForegroundColor White
Write-Host " [*] Ban chi can COPY LINK va gui cho moi nguoi xem tren dien thoai/may tinh!" -ForegroundColor Yellow
Write-Host ""

$cloudflaredPath = Join-Path $PSScriptRoot "cloudflared.exe"
if (Test-Path -LiteralPath $cloudflaredPath) {
    & $cloudflaredPath tunnel --url http://127.0.0.1:8765
} else {
    Write-Host "Khong tim thay cloudflared.exe. Dang dung du phong qua npx localtunnel..." -ForegroundColor Yellow
    npx localtunnel --port 8765
}

Read-Host "Nhan Enter de thoat"
