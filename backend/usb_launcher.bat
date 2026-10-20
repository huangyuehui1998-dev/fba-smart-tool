@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   FBA 智能装箱工具 - U盘便携版
echo ========================================
echo.
echo 正在启动，浏览器将自动打开...
echo 地址: http://localhost:8501
echo.
echo 【退出】关闭本黑色窗口即可停止服务
echo.

if not exist "FBAWizard.exe" (
  echo [错误] 未找到 FBAWizard.exe，请确认 U 盘文件完整。
  pause
  exit /b 1
)

FBAWizard.exe
if errorlevel 1 (
  echo.
  echo [错误] 程序异常退出，请查看上方报错信息。
  pause
)
