@echo off
title ERINX Drive Organizer - Launcher
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
    echo [X] Walang Python na nakita.
    echo     I-install mula sa https://www.python.org/downloads/
    echo     I-check ang "Add python.exe to PATH" sa installer.
    goto :fail
)
%PY% -c "import tkinter" >nul 2>nul
if errorlevel 1 (
    echo [X] Kulang ang Tkinter. I-run ulit ang Python installer, piliin "Modify",
    echo     at i-check ang "tcl/tk and IDLE".
    goto :fail
)
echo Binubuksan ang ERINX Drive Organizer...
%PY% "%~dp0drive_organizer.py"
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo  May problema. I-screenshot ang window na ito at ipadala kay Claude.
pause
exit /b 1
