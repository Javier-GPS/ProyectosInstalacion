@echo off
setlocal

:: ════════════════════════════════════════════════════════════════════════════
:: SALVI GIS — Lanzador con autoinstalación
:: ════════════════════════════════════════════════════════════════════════════

:: Si se relanzó en modo silencioso, ir directo a los servidores
if "%~1"=="silent" goto :run_servers

:: ── ¿Está Python instalado? ──────────────────────────────────────────────────
set "PYTHON="
python --version >nul 2>&1
if not errorlevel 1 set "PYTHON=python"
if not defined PYTHON (
    python3 --version >nul 2>&1
    if not errorlevel 1 set "PYTHON=python3"
)

:: Si Python ya está, relanzar en silencio directamente
if defined PYTHON goto :relaunch_silent

:: ── Python NO encontrado — mostrar ventana de instalación ────────────────────
echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║           SALVI GIS  —  Primera instalacion          ║
echo  ╚══════════════════════════════════════════════════════╝
echo.
echo  Python no esta instalado en este equipo.
echo  Se instalara automaticamente. Espera un momento...
echo.

:: Intentar con winget (disponible en Windows 10/11 actualizado)
winget --version >nul 2>&1
if not errorlevel 1 (
    echo  [1/2] Instalando Python 3.12 con winget...
    winget install Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    goto :verify_python
)

:: Fallback: descargar instalador oficial de python.org
echo  [1/2] Descargando Python 3.12 desde python.org...
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe' -OutFile '%TEMP%\py_setup.exe' -UseBasicParsing"
if not exist "%TEMP%\py_setup.exe" (
    echo.
    echo  [ERROR] No se pudo descargar Python.
    echo  Instálalo manualmente desde: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)
echo  Instalando...
"%TEMP%\py_setup.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1
del "%TEMP%\py_setup.exe" >nul 2>&1

:verify_python
echo  [2/2] Verificando instalacion...
python --version >nul 2>&1
if not errorlevel 1 (
    echo.
    echo  Python instalado correctamente.
    echo  Iniciando SALVI GIS...
    timeout /t 2 >nul
    goto :relaunch_silent
)
:: Winget puede instalar pero el PATH aun no se actualiza en esta sesion
:: Al relanzar con PowerShell el nuevo proceso ya tiene el PATH correcto
echo.
echo  Instalacion completada. Iniciando SALVI GIS...
timeout /t 2 >nul
goto :relaunch_silent

:relaunch_silent
powershell -windowstyle hidden -command "Start-Process '%~f0' -ArgumentList 'silent' -WindowStyle Hidden"
exit

:: ════════════════════════════════════════════════════════════════════════════
:run_servers
:: (A partir de aqui todo corre en segundo plano sin ventana)
:: ════════════════════════════════════════════════════════════════════════════

:: ── Detectar Chrome ───────────────────────────────────────────────────────────
set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe"       set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"  set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe"        set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"

:: ── Detectar Python ───────────────────────────────────────────────────────────
set "PYTHON="
python --version >nul 2>&1
if not errorlevel 1 set "PYTHON=python"
if not defined PYTHON (
    python3 --version >nul 2>&1
    if not errorlevel 1 set "PYTHON=python3"
)

:: ── Instalar paquetes Python si faltan ────────────────────────────────────────
if defined PYTHON (
    for %%P in (ezdxf openpyxl) do (
        %PYTHON% -c "import %%P" >nul 2>&1
        if errorlevel 1 (
            %PYTHON% -m pip install %%P --quiet --no-warn-script-location >nul 2>&1
        )
    )
)

:: ── Cerrar instancias previas en puertos 8732 y 8733 ─────────────────────────
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8732 " ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8733 " ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)
timeout /t 1 >nul

:: ── Arrancar servidores ───────────────────────────────────────────────────────
if defined PYTHON (
    cd /d "%~dp0"
    start /b %PYTHON% api_server.py
    start /b %PYTHON% -m http.server 8732
    goto :open_browser
)

npx --version >nul 2>&1
if not errorlevel 1 (
    cd /d "%~dp0"
    start /b npx http-server -p 8732 --cors
    goto :open_browser
)

exit

:open_browser
timeout /t 2 >nul
if defined CHROME (
    start "" "%CHROME%" "http://localhost:8732/SALVI GIS.html"
) else (
    start "" "http://localhost:8732/SALVI GIS.html"
)
exit
