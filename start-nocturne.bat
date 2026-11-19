@echo off
setlocal
cd /d "%~dp0"
set "TMP=%~dp0.tmp\runtime"
set "TEMP=%TMP%"
if not exist "%TMP%" mkdir "%TMP%"
set "PYTHON_EXE=D:\Python\python.exe"
if not exist "%PYTHON_EXE%" (
  echo Nocturne Python interpreter not found: %PYTHON_EXE%
  pause
  exit /b 1
)
echo Starting Nocturne Memory (Dashboard + REST API + MCP HTTP)...
echo Dashboard: http://127.0.0.1:8233/
echo API docs:  http://127.0.0.1:8233/api/docs
echo MCP:       http://127.0.0.1:8233/mcp
"%PYTHON_EXE%" "%~dp0backend\run_sse.py"
pause
