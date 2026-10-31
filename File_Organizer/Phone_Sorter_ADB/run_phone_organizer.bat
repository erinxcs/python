@echo off
title Phone File Organizer - Launcher
cd /d "%~dp0"

echo ============================================
echo   Phone File Organizer - checking setup...
echo ============================================
echo.

rem ---- 1. Find Python ------------------------------------------------
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [X] Walang Python na nakita.
    echo     I-install mula sa https://www.python.org/downloads/
    echo     IMPORTANTE: i-check ang "Add python.exe to PATH" sa installer.
    goto :fail
)
echo [OK] Python: %PY%

rem ---- 2. Check Tkinter (the window library) -------------------------
%PY% -c "import tkinter" >nul 2>nul
if errorlevel 1 (
    echo [X] Kulang ang Tkinter sa Python mo.
    echo     I-run ulit ang Python installer, piliin "Modify",
    echo     at i-check ang "tcl/tk and IDLE".
    goto :fail
)
echo [OK] Tkinter

rem ---- 3. Find adb, download it if missing ---------------------------
where adb >nul 2>nul && goto :adb_ok
if exist "%~dp0platform-tools\adb.exe" goto :adb_ok

echo [..] Walang adb. Dina-download ang Android platform-tools mula sa Google...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "Invoke-WebRequest 'https://dl.google.com/android/repository/platform-tools-latest-windows.zip' -OutFile '%~dp0platform-tools.zip';" ^
  "Expand-Archive '%~dp0platform-tools.zip' -DestinationPath '%~dp0' -Force;" ^
  "Remove-Item '%~dp0platform-tools.zip'"
if not exist "%~dp0platform-tools\adb.exe" (
    echo [X] Hindi ma-download ang adb. I-check ang internet, tapos subukan ulit.
    goto :fail
)

:adb_ok
echo [OK] adb
echo.
echo Binubuksan ang app...
echo.

rem ---- 4. Run the app ------------------------------------------------
%PY% "%~dp0phone_organizer.py"
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo --------------------------------------------
echo  May problema. I-screenshot ang window na ito
echo  at ipadala kay Claude.
echo --------------------------------------------
pause
exit /b 1
