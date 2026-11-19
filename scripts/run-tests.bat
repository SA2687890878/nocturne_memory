@echo off
setlocal
cd /d "%~dp0.." || exit /b 1

if not exist ".tmp\pytest-temp" mkdir ".tmp\pytest-temp"
if errorlevel 1 exit /b 1
set "TEMP=%CD%\.tmp\pytest-temp"
set "TMP=%CD%\.tmp\pytest-temp"
set "TMPDIR=%CD%\.tmp\pytest-temp"
set "PYTHONPATH=%CD%\backend"

if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto :venv_failed
)

".venv\Scripts\python.exe" -c "import pytest, pytest_asyncio, pytest_cov, fastapi, sqlalchemy, aiosqlite, asyncpg, mcp, pypinyin" >nul 2>&1
if errorlevel 1 goto :install_deps

goto :run_tests

:install_deps
echo Installing Nocturne backend and test dependencies...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --retries 2 --timeout 15 -r backend\requirements.txt -r backend\requirements-dev.txt
if errorlevel 1 goto :install_failed

:run_tests
set "TEST_TARGET=backend/tests"
for %%A in (%*) do if exist "%%~A" set "TEST_TARGET="
if defined TEST_TARGET (
    ".venv\Scripts\python.exe" -m pytest backend/tests %*
) else (
    ".venv\Scripts\python.exe" -m pytest %*
)
set "TEST_EXIT=%ERRORLEVEL%"
exit /b %TEST_EXIT%

:venv_failed
echo ERROR: Failed to create the project virtual environment.
exit /b 1

:install_failed
echo ERROR: Dependency installation failed. Check network or package index settings.
exit /b 1
