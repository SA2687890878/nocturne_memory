@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 goto :python_missing
where npm >nul 2>&1
if errorlevel 1 goto :npm_missing
python -m uvicorn --version >nul 2>&1
if errorlevel 1 goto :uvicorn_missing
if not exist "%~dp0frontend\node_modules\.bin\vite.cmd" goto :vite_missing

rem Stop previous instances: window title first, then whoever still holds the port.
call :stop_window "Nocturne Backend"
call :stop_window "Nocturne Frontend"
call :kill_port 8233
call :kill_port 3000

echo Starting backend on 127.0.0.1:8233...
start "Nocturne Backend" /D "%~dp0backend" "%ComSpec%" /k "python -m uvicorn main:app --host 127.0.0.1 --port 8233 --reload --no-access-log"

echo Starting frontend on 127.0.0.1:3000...
start "Nocturne Frontend" /D "%~dp0frontend" "%ComSpec%" /k "npm run dev -- --host 127.0.0.1 --strictPort"

echo.
echo Frontend: http://127.0.0.1:3000/
echo Backend:  http://127.0.0.1:8233
echo Close the backend and frontend command windows to stop the services.
echo Note: previous command windows may stay open but idle; close them manually.
pause
exit /b 0

:python_missing
echo Python was not found in PATH.
echo Install Python or add it to PATH, then run this file again.
pause
exit /b 1

:npm_missing
echo npm was not found in PATH.
echo Install Node.js, then run this file again.
pause
exit /b 1

:uvicorn_missing
echo Uvicorn is missing from the active Python environment.
echo Install backend dependencies with: python -m pip install -r backend\requirements.txt
pause
exit /b 1

:vite_missing
echo Frontend dependencies are missing.
echo Install them with: cd frontend ^&^& npm install
pause
exit /b 1

rem ---------------------------------------------------------------------------
rem Helpers
rem ---------------------------------------------------------------------------

:stop_window
taskkill /FI "WINDOWTITLE eq %~1*" /T /F >nul 2>&1
exit /b 0

:kill_port
set "KILL_PORT=%~1"
set "KILLED="
for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /C:":%KILL_PORT% " ^| findstr /C:"LISTENING"') do (
    echo   port %KILL_PORT%: stopping PID %%P
    taskkill /PID %%P /T /F >nul 2>&1
    set "KILLED=1"
)
if defined KILLED call :wait_port_free %KILL_PORT%
exit /b 0

:wait_port_free
for /l %%I in (1,1,10) do (
    netstat -ano -p tcp | findstr /C:":%~1 " | findstr /C:"LISTENING" >nul
    if errorlevel 1 exit /b 0
    ping -n 2 127.0.0.1 >nul
)
echo   warning: port %~1 is still in use
exit /b 0
