@echo off
rem ==========================================================================
rem   MIKASA - Universal Setup & Control Deck
rem   Built by AM Dimension Company And Creators - AYUSH AND MAYANK
rem
rem   First run  -> Guided 1-click setup (.venv + 4 packages + API key + icon)
rem   Later runs -> Interactive Control Deck (change/test key, check packages,
rem                 run 43 diagnostics + live voice test, launch Mikasa)
rem ==========================================================================
chcp 65001 >nul 2>nul
title MIKASA - Setup ^& Control Deck
cd /d "%~dp0"
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

set "PY="

rem 1. Prefer py launcher
where py >nul 2>nul && set "PY=py -3"

rem 2. Try python on PATH (skip the fake 0-byte WindowsApps Store redirector)
if not defined PY (
    for /f "delims=" %%I in ('where python 2^>nul') do (
        echo "%%I" | find /i "WindowsApps" >nul
        if errorlevel 1 if not defined PY set "PY=%%I"
    )
)

rem 3. Check standard LocalAppData Python installs even if user forgot PATH box
if not defined PY (
    for %%V in (313 312 311 310 39) do (
        if not defined PY if exist "%LocalAppData%\Programs\Python\Python%%V\python.exe" (
            set "PY=%LocalAppData%\Programs\Python\Python%%V\python.exe"
        )
    )
)

if not defined PY goto :nopython

"%PY%" -c "import sys;raise SystemExit(0 if sys.version_info>=(3,9) else 1)" >nul 2>nul
if errorlevel 1 (
    if "%PY%"=="py -3" (
        py -3 -c "import sys;raise SystemExit(0 if sys.version_info>=(3,9) else 1)" >nul 2>nul
        if errorlevel 1 goto :oldpython
        py -3 "%~dp0setup.py" %*
        set "RC=%ERRORLEVEL%"
        goto :done
    )
    goto :oldpython
)

if "%PY%"=="py -3" (
    py -3 "%~dp0setup.py" %*
) else (
    "%PY%" "%~dp0setup.py" %*
)
set "RC=%ERRORLEVEL%"

:done
echo.
if not "%RC%"=="0" (
    echo   Setup ruk gaya. Upar likha hai kya karna hai.
    echo.
)
echo   Window band karne ke liye koi bhi key dabao...
pause >nul
exit /b %RC%


:nopython
echo.
echo   +--------------------------------------------------------------------+
echo   ^|  PYTHON NAHI MILA                                                  ^|
echo   +--------------------------------------------------------------------+
echo.
echo   Mikasa ko Python 3.9+ chahiye (sirf ek baar install karna hota hai).
echo.
echo        https://www.python.org/downloads/
echo.
echo   Install karte waqt sabse neeche ye box TICK karna mat bhoolna:
echo.
echo        [x] Add python.exe to PATH
echo.
echo   Install hone ke baad wapas INSTALL.bat par double-click karo.
echo.
start "" "https://www.python.org/downloads/"
pause
exit /b 1


:oldpython
echo.
echo   Python mila, par purana version hai.
echo.
echo   Mikasa ko Python 3.9 ya usse naya chahiye (3.11 / 3.12 best hai).
echo   Naya yahan se download karo:  https://www.python.org/downloads/
echo.
start "" "https://www.python.org/downloads/"
pause
exit /b 1
