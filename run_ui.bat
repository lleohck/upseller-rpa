@echo off
setlocal

set SCRIPT_DIR=%~dp0

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
