@echo off
rem Chay VietSafe (Windows): bam dup file nay. Mo http://127.0.0.1:8765
cd /d "%~dp0.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
