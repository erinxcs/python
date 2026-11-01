@echo off
title ERINX Face Sorter - Launcher
cd /d "%~dp0"

REM ---------- Hanapin ang Python ----------
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY goto :nopython
%PY% -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul
if errorlevel 1 goto :oldpython

REM ---------- I-check ang libraries; i-install kung kulang ----------
%PY% -c "import insightface, sklearn, PIL, tqdm" >nul 2>nul
if not errorlevel 1 goto :askfolder
echo Kulang pa ang libraries na kailangan ng Face Sorter.
choice /c YN /m "I-install na ngayon? Kailangan ng internet"
if errorlevel 2 goto :fail
%PY% -m pip install --upgrade pip
%PY% -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto :fail

:askfolder
echo.
set "FOLDER="
set /p "FOLDER=I-paste ang folder path ng photos: "
if not defined FOLDER goto :askfolder
set "FOLDER=%FOLDER:"=%"
if "%FOLDER:~-1%"=="\" set "FOLDER=%FOLDER%."
if not exist "%FOLDER%\" (
    echo [X] Hindi makita ang folder na iyan. Subukan ulit.
    goto :askfolder
)
set "THR=0.50"

:menu
echo.
echo ================= ERINX FACE SORTER =================
echo  Folder:    %FOLDER%
echo  Threshold: %THR%
echo -----------------------------------------------------
echo  1. Silip muna - dry run, walang ililipat
echo  2. I-sort na - ililipat ang photos
echo  3. Undo - ibalik lahat sa dati
echo  4. Palitan ang threshold
echo  5. Ibang folder
echo  6. Exit
echo =====================================================
choice /c 123456 /n /m "Pili [1-6]: "
if errorlevel 6 exit /b 0
if errorlevel 5 goto :askfolder
if errorlevel 4 goto :threshold
if errorlevel 3 goto :undo
if errorlevel 2 goto :sort
goto :dryrun

:dryrun
%PY% "%~dp0face_sorter.py" "%FOLDER%" --dry-run --threshold %THR%
goto :after

:sort
%PY% "%~dp0face_sorter.py" "%FOLDER%" --threshold %THR%
goto :after

:undo
%PY% "%~dp0face_sorter.py" "%FOLDER%" --undo
goto :after

:threshold
echo.
echo  Mas mababa = mas mahigpit, mas maraming Face folder. Hal. 0.40
echo  Mas mataas = mas maluwag, mas kaunting Face folder.  Hal. 0.60
set /p "THR=Bagong threshold [%THR%]: "
goto :menu

:after
if errorlevel 1 (
    echo.
    echo  May error. I-screenshot ang window na ito at ipadala kay Claude.
)
echo.
pause
goto :menu

:nopython
echo [X] Walang Python na nakita.
echo     I-install mula sa https://www.python.org/downloads/ - 3.10 pataas
echo     I-check ang "Add python.exe to PATH" sa installer.
goto :fail

:oldpython
echo [X] Luma ang Python mo. Kailangan ng Python 3.10 pataas.
echo     I-install mula sa https://www.python.org/downloads/
goto :fail

:fail
echo.
echo  May problema. I-screenshot ang window na ito at ipadala kay Claude.
pause
exit /b 1
