@echo off
setlocal
cd /d "%~dp0"

echo [0/4] Closing any running FBAWizard instances...
taskkill /F /IM FBAWizard.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo [1/4] Preparing virtual environment...
if not exist ".venv" py -m venv .venv
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q
pip install pyinstaller -q

echo [2/4] Building portable package (may take several minutes)...
if exist "dist\FBAWizard" (
  echo       Removing old dist\FBAWizard ...
  rmdir /s /q "dist\FBAWizard" 2>nul
)
.venv\Scripts\pyinstaller.exe --noconfirm FBAWizard.spec
if errorlevel 1 (
  echo [WARN] dist locked, building to dist2\FBAWizard instead...
  .venv\Scripts\pyinstaller.exe --noconfirm --distpath dist2 FBAWizard.spec
  set "OUT=dist2\FBAWizard"
) else (
  set "OUT=dist\FBAWizard"
)

echo [3/4] Copying config, templates, launcher...
if not exist "%OUT%\templates" mkdir "%OUT%\templates"
if not exist "%OUT%\config" mkdir "%OUT%\config"
if not exist "%OUT%\.streamlit" mkdir "%OUT%\.streamlit"
xcopy /E /I /Y "templates\*" "%OUT%\templates\" >nul
xcopy /E /I /Y "config\*" "%OUT%\config\" >nul
copy /Y ".streamlit\config.toml" "%OUT%\.streamlit\config.toml" >nul
copy /Y "usb_launcher.bat" "%OUT%\启动FBA工具.bat" >nul
copy /Y "dist2\FBAWizard\使用说明.txt" "%OUT%\使用说明.txt" >nul 2>&1

echo [4/4] Done.
echo.
echo ========================================
echo  Portable folder: %OUT%\
echo  Copy the ENTIRE FBAWizard folder to USB.
echo  Double-click: 启动FBA工具.bat
echo ========================================
pause
