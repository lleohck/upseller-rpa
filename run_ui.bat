@echo off
setlocal

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"
set VENV_PY=%SCRIPT_DIR%\.venv\Scripts\python.exe

if exist "%VENV_PY%" (
  "%VENV_PY%" "%SCRIPT_DIR%run_ui.py" %*
  exit /b %errorlevel%
)

if defined VIRTUAL_ENV if exist "%VIRTUAL_ENV%\Scripts\python.exe" (
  "%VIRTUAL_ENV%\Scripts\python.exe" "%SCRIPT_DIR%run_ui.py" %*
  exit /b %errorlevel%
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%SCRIPT_DIR%run_ui.py" %*
  exit /b %errorlevel%
)

where python >nul 2>nul
if %errorlevel%==0 (
  python "%SCRIPT_DIR%run_ui.py" %*
  exit /b %errorlevel%
)

echo Python nao encontrado no PATH.
exit /b 1
