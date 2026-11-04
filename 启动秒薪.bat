@echo off
cd /d "%~dp0"
if exist "%~dp0秒薪.exe" (
  start "" "%~dp0秒薪.exe"
  exit /b 0
)
where py >nul 2>&1
if errorlevel 1 (
  echo 直接双击 秒薪.exe
  pause
  exit /b 1
)
py -3 -c "import webview" >nul 2>&1
if errorlevel 1 py -3 -m pip install -q -r "%~dp0requirements.txt"
start "" py -3w "%~dp0秒薪.pyw"
