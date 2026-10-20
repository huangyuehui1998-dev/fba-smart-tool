@echo off
setlocal
cd /d "%~dp0"

echo [1/4] Preparing virtual environment...
if not exist ".venv" py -m venv .venv
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q
pip install pyinstaller uvicorn -q

echo [2/4] Syncing frontend static files...
if exist "dist" rmdir /s /q "dist"
mkdir dist
xcopy /E /I /Y "..\frontend\dist\client\*" "dist\" >nul

echo [3/4] Building portable package with PyInstaller...
.venv\Scripts\pyinstaller.exe --noconfirm FBAWizard_V1.6.spec

if errorlevel 1 (
  echo [ERROR] PyInstaller build failed!
  exit /b 1
)

set "OUT=dist\FBAWizard_V1.6"

echo [4/4] Copying config, templates, launcher...
if not exist "%OUT%\templates" mkdir "%OUT%\templates"
if not exist "%OUT%\config" mkdir "%OUT%\config"
xcopy /E /I /Y "templates\*" "%OUT%\templates\" >nul
xcopy /E /I /Y "config\*" "%OUT%\config\" >nul

:: Create a launch bat
echo @echo off > "%OUT%\启动FBA工具.bat"
echo cd /d "%%~dp0" >> "%OUT%\启动FBA工具.bat"
echo start "" "FBAWizard_V1.6.exe" >> "%OUT%\启动FBA工具.bat"

copy /Y "..\FBA_Smart_Tool_工作流与运行逻辑.txt" "%OUT%\工作流与运行逻辑.txt" >nul 2>&1
copy /Y "使用说明.txt" "%OUT%\使用说明.txt" >nul 2>&1

echo.
echo ========================================
echo  Portable folder created at: %OUT%\
echo  To zip: Right click %OUT% -^> Send to -^> Compressed (zipped) folder
echo ========================================
