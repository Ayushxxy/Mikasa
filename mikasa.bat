@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>nul
cd /d "%~dp0"
title Mikasa

rem ==========================================================================
rem   Mikasa - One-File Launcher & First-Time Setup
rem   - First run (missing .venv, packages, or API key): opens Guided Setup.
rem   - Every launch after: opens her dark room silently via pythonw.
rem   - Run `mikasa.bat --setup` or `python setup.py` anytime for Control Deck.
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

if not defined PY goto :nopython

rem Explicit setup / menu flags open the interactive Control Deck
if /I "%~1"=="--setup" goto :runsetup
if /I "%~1"=="--menu"  goto :runsetup
if /I "%~1"=="setup"   goto :runsetup

rem Check the 4 required packages
"%PY%" -c "import PyQt6, numpy, sounddevice; from google import genai" >nul 2>nul
if errorlevel 1 goto :nopkgs

rem Check that a Gemini API key is configured
"%PY%" -c "import sys; sys.path.insert(0, 'core'); import live; raise SystemExit(0 if live.find_api_key() else 1)" >nul 2>nul
if errorlevel 1 goto :nokey

rem Everything is ready -> launch her dark room silently (no console behind her)
if defined PYW (
    start "" "%PYW%" "%~dp0core\app.py" %*
    exit /b 0
)
for /f "delims=" %%W in ('"%PY%" -c "import sys, pathlib; p = pathlib.Path(sys.executable).with_name('pythonw.exe'); print(p if p.exists() else '')" 2^>nul') do set "PYW=%%W"
if defined PYW (
    start "" "%PYW%" "%~dp0core\app.py" %*
    exit /b 0
)

"%PY%" "%~dp0core\app.py" %*
if errorlevel 1 (
    echo.
    echo   Mikasa stopped unexpectedly. Check config\mikasa-error.txt if needed.
    pause
)
exit /b 0

:runsetup
"%PY%" "%~dp0setup.py" --menu
echo.
pause
exit /b %ERRORLEVEL%

:nopkgs
echo.
echo   First time here - setting up Mikasa's room for you...
echo   (Fallback manual command: python -m pip install PyQt6 numpy sounddevice google-genai)
echo.
"%PY%" "%~dp0setup.py"
echo.
pause
exit /b %ERRORLEVEL%

:nokey
echo.
echo   Almost ready - let's add your free Gemini API key...
echo.
"%PY%" "%~dp0setup.py" --menu
echo.
pause
exit /b %ERRORLEVEL%

:nopython
echo.
echo   ==================================================================
echo     Python 3.9+ was not found on this Windows PC
echo   ==================================================================
echo.
echo     1. Download Python 3.11 or 3.12 from:
echo        https://www.python.org/downloads/
echo.
echo     2. IMPORTANT: Tick  [x] Add python.exe to PATH  at the bottom
echo        of the installer, then click Install Now.
echo.
echo     3. Come back and double-click mikasa.bat again!
echo.
set /p "_OPEN=  Open python.org download page in your browser now? [Y/n]: "
if /I not "%_OPEN%"=="n" start "" "https://www.python.org/downloads/"
echo.
pause
exit /b 1
