param([int]$Port = 8791)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$env:PYTHONUTF8 = '1'
Write-Host "Flood scenario: http://127.0.0.1:$Port/flood-simulator.html"
& (Join-Path $repo 'scripts\start.ps1') -Port $Port
