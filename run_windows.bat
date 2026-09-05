@echo off
setlocal
cd /d "%~dp0"
set "FUTURES_PY="
python -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>&1
if not errorlevel 1 set "FUTURES_PY=python"
if defined FUTURES_PY goto run
py -3 -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>&1
if not errorlevel 1 set "FUTURES_PY=py -3"
if defined FUTURES_PY goto run
echo Python 3.10 or newer was not found. Install from https://www.python.org/downloads/windows/
set "FUTURES_EXIT=1"
goto finish
:run
%FUTURES_PY% futures.py --test
if errorlevel 1 goto failed
%FUTURES_PY% futures.py --demo --out results
if errorlevel 1 goto failed
echo Synthetic demo completed. Output: "%CD%\results"
echo Existing results in that folder have been replaced.
set "FUTURES_EXIT=0"
goto finish
:failed
echo Run failed. See the error above.
set "FUTURES_EXIT=1"
:finish
if /i not "%~1"=="--no-pause" pause
exit /b %FUTURES_EXIT%
