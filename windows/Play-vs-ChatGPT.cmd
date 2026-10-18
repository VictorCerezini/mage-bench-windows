@echo off
powershell.exe -NoLogo -NoProfile -File "%~dp0Play-vs-ChatGPT.ps1"
if errorlevel 1 pause
