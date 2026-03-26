@echo off
setlocal enabledelayedexpansion

set "AUTO_PAUSE=1"
if /i "%~1"=="--no-pause" set "AUTO_PAUSE=0"

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR:~0,-1%"
set "VENV_PY=%PROJECT_DIR%\.venv\Scripts\python.exe"
set "APP_NAME=upseller-rpa-ui"
set "DIST_APP_DIR=%PROJECT_DIR%\dist\%APP_NAME%"
set "BROWSERS_DIR=%PROJECT_DIR%\ms-playwright"
set "LOG_FILE=%PROJECT_DIR%\build_windows_exe.log"

echo ============================================ > "%LOG_FILE%"
echo Build iniciado em %date% %time% >> "%LOG_FILE%"
echo Projeto: %PROJECT_DIR% >> "%LOG_FILE%"
echo ============================================ >> "%LOG_FILE%"

echo.
echo [INFO] Log completo: "%LOG_FILE%"
echo.

if not exist "%VENV_PY%" (
  call :die ".venv nao encontrado. Crie o ambiente e instale dependencias."
)

"%VENV_PY%" -c "import PyInstaller" >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
  call :die "PyInstaller nao encontrado no .venv. Rode: .venv\Scripts\python -m pip install -r requirements.txt"
)

call :log "[1/5] Preparando browser do Playwright em pasta local..."
set "PLAYWRIGHT_BROWSERS_PATH=%BROWSERS_DIR%"
"%VENV_PY%" -m playwright install chromium >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
  call :die "Falha ao instalar browser Chromium do Playwright. Veja o log."
)

call :log "[2/5] Gerando executavel (onedir)..."
"%VENV_PY%" -m PyInstaller --noconfirm --clean --onedir --name %APP_NAME% ^
  --collect-all streamlit ^
  --collect-all playwright ^
  --hidden-import rpa ^
  --hidden-import rpa.variant_runner ^
  --hidden-import variant_job_worker ^
  --hidden-import login_manual_worker ^
  --add-data "%PROJECT_DIR%\ui_app.py;." ^
  --add-data "%PROJECT_DIR%\.env.example;." ^
  "%PROJECT_DIR%\run_ui.py" >> "%LOG_FILE%" 2>&1

if %errorlevel% neq 0 (
  call :die "Falha no build do executavel. Veja o log."
)

if not exist "%DIST_APP_DIR%" (
  call :die "Pasta final nao encontrada: %DIST_APP_DIR%"
)

call :log "[3/5] Copiando browsers para o pacote final..."
if exist "%DIST_APP_DIR%\ms-playwright" (
  rmdir /s /q "%DIST_APP_DIR%\ms-playwright" >> "%LOG_FILE%" 2>&1
)
robocopy "%BROWSERS_DIR%" "%DIST_APP_DIR%\ms-playwright" /E >> "%LOG_FILE%" 2>&1
if %errorlevel% geq 8 (
  call :die "Falha ao copiar pasta ms-playwright. Veja o log."
)

if exist "%PROJECT_DIR%\.env.example" (
  copy /Y "%PROJECT_DIR%\.env.example" "%DIST_APP_DIR%\.env.example" >> "%LOG_FILE%" 2>&1
)
if exist "%PROJECT_DIR%\README.md" (
  copy /Y "%PROJECT_DIR%\README.md" "%DIST_APP_DIR%\README.md" >> "%LOG_FILE%" 2>&1
)

call :log "[4/5] Criando launcher start.bat..."
(
echo @echo off
echo setlocal
echo set "APP_DIR=%%~dp0"
echo set "PLAYWRIGHT_BROWSERS_PATH=%%APP_DIR%%ms-playwright"
echo if not exist "%%APP_DIR%%.env" if exist "%%APP_DIR%%.env.example" copy "%%APP_DIR%%.env.example" "%%APP_DIR%%.env" ^>nul
echo "%%APP_DIR%%upseller-rpa-ui.exe" %%*
) > "%DIST_APP_DIR%\start.bat"

call :log "[5/5] Build concluido com sucesso."
call :log "Pacote final: %DIST_APP_DIR%"
call :log "No computador destino, execute start.bat"
exit /b 0

:log
echo %~1
echo %~1 >> "%LOG_FILE%"
exit /b 0

:die
echo [ERRO] %~1
echo [ERRO] %~1 >> "%LOG_FILE%"
echo [ERRO] Consulte o log: "%LOG_FILE%"
if "%AUTO_PAUSE%"=="1" pause
exit /b 1
