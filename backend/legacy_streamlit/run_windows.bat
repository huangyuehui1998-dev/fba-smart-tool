@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo  FBA 智能装箱工具 - U盘便携启动
echo ========================================

if exist "dist\FBAWizard\FBAWizard.exe" (
  echo [INFO] 使用已打包版本...
  start "" "dist\FBAWizard\FBAWizard.exe"
  exit /b 0
)

if not exist ".venv\Scripts\python.exe" (
  echo [INFO] 首次运行，正在创建虚拟环境...
  py -m venv .venv
  if errorlevel 1 (
    echo [ERROR] 未找到 Python。请安装 Python 3.10+ 或使用 build_portable_windows.bat 打包。
    pause
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q

echo [INFO] 启动中，浏览器将自动打开 http://localhost:8501
python launcher.py
pause
