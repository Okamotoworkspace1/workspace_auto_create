@echo off
rem YouTube downloader for Windows: double-click to install (or update).
rem The installer itself is install.ps1. It is read as UTF-8 here, because
rem "powershell -File" would read it as Shift_JIS and break the Japanese text.
set "YTDL_SRC=%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex ([IO.File]::ReadAllText((Join-Path $env:YTDL_SRC 'windows\install.ps1')))"
if errorlevel 1 pause
