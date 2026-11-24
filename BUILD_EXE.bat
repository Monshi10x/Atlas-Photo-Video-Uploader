@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Run START.bat first to install the app dependencies.
 pause
 exit /b 1
)
.venv\Scripts\python.exe -m pip install "pyinstaller>=6,<7"
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name AtlasPhotoStudio --collect-all keyring --collect-all imageio_ffmpeg --hidden-import keyring.backends.Windows app.py
if errorlevel 1 goto fail
echo Created dist\AtlasPhotoStudio.exe
pause
exit /b 0
:fail
echo Build failed. Read the error above.
pause
exit /b 1
