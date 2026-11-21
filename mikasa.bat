@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>nul
cd /d "%~dp0"
title Mikasa

rem ==========================================================================
rem   Mikasa - Direct Launcher
rem   If packages or API key are missing, offers to launch INSTALL.bat right
rem   here so a new user never hits a dead window.
rem ==========================================================================

set "PY="
set "PYW="

if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY=%~dp0.venv\Scripts\python.exe"
    if exist "%~dp0.venv\Scripts\pythonw.exe" set "PYW=%~dp0.venv\Scripts\pythonw.exe"
)

if not defined PY (
    where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
    for /f "delims=" %%I in ('where python 2^>nul') do (
        echo "%%I" | find /i "WindowsApps" >nul
        if errorlevel 1 if not defined PY set "PY=%%I"
    )
)
if not defined PY (
    for %%V in (313 312 311 310 39) do (
        if not defined PY if exist "%LocalAppData%\Programs\Python\Python%%V\python.exe" (
            set "PY=%LocalAppData%\Programs\Python\Python%%V\python.exe"
        )
    )
)

if not defined PY goto :needsetup

if not defined PYW (
    for %%V in (313 312 311 310 39) do (
        if not defined PYW if exist "%LocalAppData%\Programs\Python\Python%%V\pythonw.exe" (
            set "PYW=%LocalAppData%\Programs\Python\Python%%V\pythonw.exe"
        )
    )
)
if not defined PYW (
    where pythonw >nul 2>nul && set "PYW=pythonw"
)
if not defined PYW set "PYW=%PY%"

if "%PY%"=="py -3" (
    py -3 -c "import PyQt6, numpy, sounddevice, google.genai" >nul 2>nul
) else (
    "%PY%" -c "import PyQt6, numpy, sounddevice, google.genai" >nul 2>nul
)
if errorlevel 1 goto :needsetup

if not exist "%~dp0config\api_keys.json" (
    if "%GEMINI_API_KEY%"=="" if "%GOOGLE_API_KEY%"=="" goto :needkey
)

if "%PYW%"=="py -3" (
    start "" pyw -3 "%~dp0app.py"
) else (
    start "" "%PYW%" "%~dp0app.py"
)
exit /b 0


:needsetup
echo.
echo   First-time setup abhi baaki hai (packages install nahi hue).
echo   INSTALL.bat abhi chala raha hoon...
echo.
call "%~dp0INSTALL.bat"
exit /b %ERRORLEVEL%


:needkey
echo.
echo   Gemini API key abhi set nahi hai.
echo   Setup Control Deck khol raha hoon taaki key paste kar sako...
echo.
call "%~dp0INSTALL.bat" --menu
exit /b %ERRORLEVEL%
