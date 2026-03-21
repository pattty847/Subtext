@echo off
cd /d "%~dp0"
title Subtext

where uv >nul 2>nul
if errorlevel 1 (
    echo uv is not installed.
    echo Install it from: https://docs.astral.sh/uv/getting-started/installation/
    pause
    exit /b 1
)

if not exist ".venv" (
    echo Setting up environment with uv sync...
    uv sync
    if errorlevel 1 (
        echo Setup failed.
        pause
        exit /b 1
    )
)

echo.
echo  [1] Desktop app         - full local workflow with AI analysis
echo  [2] Private web service - localhost service for browser/Tailscale use
echo.
set /p pick="Choose 1 or 2: "

if "%pick%"=="2" (
    echo.
    echo Starting private web service...
    echo Local check: http://127.0.0.1:8000
    echo For phone access, pair it with Tailscale Serve.
    echo.
    uv run python run_web.py
) else (
    if not "%pick%"=="1" (
        echo Unknown option. Starting Desktop app.
        echo.
    )
    echo Launching Subtext Desktop app...
    uv run python run.py
)

if errorlevel 1 (
    echo.
    echo Application exited with an error.
    pause
)
