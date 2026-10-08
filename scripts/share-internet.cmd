@echo off
rem Tao link Internet (Cloudflare Tunnel) de chia se ban demo cho nguoi khac xem.
cd /d "%~dp0.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0share-internet.ps1"
