@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto deps
py -3 --version >nul 2>&1
if errorlevel 1 (
 echo Please install Python 3.11 or newer from https://www.python.org/downloads/windows/
 echo Include the Python launcher during installation, then run START.bat again.
 pause
 exit /b 1
)
py -3 -m venv .venv
if errorlevel 1 goto fail
:deps
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
:run
.venv\Scripts\python.exe app.py
if errorlevel 1 goto fail
exit /b 0
:fail
echo Setup or launch failed. See the error above. Check your internet connection.
pause
exit /b 1
