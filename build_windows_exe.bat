@echo off
setlocal

set SCRIPT_DIR=%~dp0
set VENV_PY=%SCRIPT_DIR%.venv\Scripts\python.exe

if not exist "%VENV_PY%" (
  echo .venv nao encontrado. Crie o ambiente e instale as dependencias primeiro.
  echo Exemplo:
  echo   py -3 -m venv .venv
  echo   .venv\Scripts\python -m pip install -r requirements.txt
  exit /b 1
)

"%VENV_PY%" -m PyInstaller --noconfirm --clean --onefile --name upseller-rpa-ui ^
  --add-data "%SCRIPT_DIR%ui_app.py;." ^
  --hidden-import rpa ^
  --hidden-import rpa.variant_runner ^
  "%SCRIPT_DIR%run_ui.py"

if %errorlevel% neq 0 (
  echo Falha no build do executavel.
  exit /b %errorlevel%
)

echo Build concluido. Executavel em dist\upseller-rpa-ui.exe
exit /b 0
