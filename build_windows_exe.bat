@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR:~0,-1%"
set "VENV_PY=%PROJECT_DIR%\.venv\Scripts\python.exe"
set "APP_NAME=upseller-rpa-ui"
set "DIST_APP_DIR=%PROJECT_DIR%\dist\%APP_NAME%"
set "BROWSERS_DIR=%PROJECT_DIR%\ms-playwright"

if not exist "%VENV_PY%" (
  echo .venv nao encontrado. Crie o ambiente e instale as dependencias primeiro.
  echo Exemplo:
  echo   py -3 -m venv .venv
  echo   .venv\Scripts\python -m pip install -r requirements.txt
  echo   .venv\Scripts\python -m playwright install chromium
  exit /b 1
)

echo [1/5] Preparando browser do Playwright em pasta local...
set "PLAYWRIGHT_BROWSERS_PATH=%BROWSERS_DIR%"
"%VENV_PY%" -m playwright install chromium
if %errorlevel% neq 0 (
  echo Falha ao instalar browser Chromium do Playwright.
  exit /b %errorlevel%
)

echo [2/5] Gerando executavel (onedir)...
"%VENV_PY%" -m PyInstaller --noconfirm --clean --onedir --name %APP_NAME% ^
  --collect-all streamlit ^
  --collect-all playwright ^
  --hidden-import rpa ^
  --hidden-import rpa.variant_runner ^
  --hidden-import variant_job_worker ^
  --hidden-import login_manual_worker ^
  --add-data "%PROJECT_DIR%\ui_app.py;." ^
  --add-data "%PROJECT_DIR%\.env.example;." ^
  "%PROJECT_DIR%\run_ui.py"

if %errorlevel% neq 0 (
  echo Falha no build do executavel.
  exit /b %errorlevel%
)

if not exist "%DIST_APP_DIR%" (
  echo Pasta final nao encontrada: %DIST_APP_DIR%
  exit /b 1
)

echo [3/5] Copiando browsers para o pacote final...
if exist "%DIST_APP_DIR%\ms-playwright" (
  rmdir /s /q "%DIST_APP_DIR%\ms-playwright"
)
robocopy "%BROWSERS_DIR%" "%DIST_APP_DIR%\ms-playwright" /E >nul
if %errorlevel% geq 8 (
  echo Falha ao copiar pasta ms-playwright.
  exit /b %errorlevel%
)

if exist "%PROJECT_DIR%\.env.example" (
  copy /Y "%PROJECT_DIR%\.env.example" "%DIST_APP_DIR%\.env.example" >nul
)
if exist "%PROJECT_DIR%\README.md" (
  copy /Y "%PROJECT_DIR%\README.md" "%DIST_APP_DIR%\README.md" >nul
)

echo [4/5] Criando launcher start.bat...
(
echo @echo off
echo setlocal
echo set "APP_DIR=%%~dp0"
echo set "PLAYWRIGHT_BROWSERS_PATH=%%APP_DIR%%ms-playwright"
echo if not exist "%%APP_DIR%%.env" if exist "%%APP_DIR%%.env.example" copy "%%APP_DIR%%.env.example" "%%APP_DIR%%.env" ^>nul
echo "%%APP_DIR%%upseller-rpa-ui.exe" %%*
) > "%DIST_APP_DIR%\start.bat"

echo [5/5] Build concluido com sucesso.
echo Pacote final: "%DIST_APP_DIR%"
echo Execute no computador destino via start.bat
exit /b 0
