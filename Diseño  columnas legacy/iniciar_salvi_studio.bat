@echo off
title Salvi Studio - Arranque

:: ── Relanzar manteniendo ventana abierta ─────────────────────────────────────
if "%1"=="keep" goto :check_admin
start "Salvi Studio" cmd /k "%~f0" keep
exit /b

:: ── Elevar privilegios si hace falta (necesario para instalar Docker) ─────────
:check_admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Solicitando permisos de administrador...
    powershell -Command "Start-Process cmd -ArgumentList '/k \"%~f0\" keep' -Verb RunAs"
    exit /b
)

:main
echo ============================================
echo   Salvi Studio - Columns - Arranque
echo ============================================
echo.

set "BACKEND_DIR=%~dp0backend"
echo Directorio backend: %BACKEND_DIR%
echo.

:: ── Comprobar que existe el directorio backend ───────────────────────────────
if not exist "%BACKEND_DIR%\docker-compose.yml" (
    echo ERROR: No se encuentra docker-compose.yml en:
    echo %BACKEND_DIR%
    pause
    exit /b 1
)

:: ── Buscar Docker ─────────────────────────────────────────────────────────────
echo [1/6] Comprobando Docker...

set "DOCKER_FOUND=0"
where docker >nul 2>&1
if %errorlevel% equ 0 set "DOCKER_FOUND=1"

if "%DOCKER_FOUND%"=="0" (
    for %%P in (
        "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
        "%LOCALAPPDATA%\Docker\Docker\resources\bin\docker.exe"
        "%ProgramW6432%\Docker\Docker\resources\bin\docker.exe"
    ) do (
        if exist %%P set "DOCKER_FOUND=1"
    )
)

if "%DOCKER_FOUND%"=="1" (
    echo        Docker encontrado.
    goto check_docker_running
)

:: ── Docker no instalado: instalarlo automaticamente ──────────────────────────
echo.
echo        Docker no esta instalado.
echo        Instalando Docker Desktop automaticamente...
echo.

:: Intentar primero con winget (Windows 10/11 moderno)
where winget >nul 2>&1
if %errorlevel% equ 0 (
    echo        Usando winget para instalar Docker Desktop...
    echo        Esto puede tardar varios minutos segun tu conexion.
    echo.
    winget install -e --id Docker.DockerDesktop --accept-source-agreements --accept-package-agreements
    if %errorlevel% equ 0 goto docker_installed_ok
    echo        winget tuvo un problema. Intentando descarga directa...
)

:: Descarga directa del instalador oficial de Docker
echo        Descargando instalador de Docker Desktop...
echo        (archivo de aprox. 500 MB, puede tardar varios minutos)
echo.
set "INSTALLER=%TEMP%\DockerDesktopInstaller.exe"
powershell -Command "& { $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://desktop.docker.com/win/main/amd64/Docker Desktop Installer.exe' -OutFile '%INSTALLER%' }"
if not exist "%INSTALLER%" (
    echo.
    echo ERROR: No se pudo descargar el instalador de Docker.
    echo Comprueba tu conexion a internet e intentalo de nuevo,
    echo o instala Docker Desktop manualmente desde:
    echo https://www.docker.com/products/docker-desktop/
    pause
    exit /b 1
)

echo        Instalador descargado. Ejecutando instalacion...
echo        Sigue las instrucciones del instalador si aparecen.
echo.
"%INSTALLER%" install --quiet --accept-license
if %errorlevel% neq 0 (
    echo.
    echo ERROR durante la instalacion de Docker Desktop.
    echo Intentalo manualmente desde:
    echo https://www.docker.com/products/docker-desktop/
    pause
    exit /b 1
)

:docker_installed_ok
echo.
echo        Docker Desktop instalado correctamente.
echo.
echo IMPORTANTE: Es posible que necesites reiniciar el ordenador
echo para que Docker funcione correctamente.
echo.
echo Presiona una tecla para continuar (si el ordenador se reinicia,
echo vuelve a ejecutar este .bat despues del reinicio).
pause

:: Refrescar PATH tras instalacion
set "PATH=%PATH%;C:\Program Files\Docker\Docker\resources\bin"

:: ── Comprobar si Docker Engine esta en marcha ─────────────────────────────────
:check_docker_running
docker version >nul 2>&1
if %errorlevel% equ 0 (
    echo        Docker Engine en marcha.
    goto start_containers
)

:: Buscar y arrancar Docker Desktop
echo        Arrancando Docker Desktop...
set "DOCKER_EXE="
for %%P in (
    "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    "%LOCALAPPDATA%\Docker\Docker Desktop.exe"
    "%LOCALAPPDATA%\Programs\Docker\Docker Desktop.exe"
    "C:\Program Files\Docker\Docker Desktop.exe"
) do (
    if exist %%P (
        set "DOCKER_EXE=%%P"
        goto launch_docker
    )
)

:launch_docker
if defined DOCKER_EXE (
    start "" %DOCKER_EXE%
) else (
    echo        No se encuentra el ejecutable de Docker Desktop.
    echo        Por favor, abre Docker Desktop manualmente.
    pause
)

echo.
echo Esperando a que Docker Engine arranque
echo (puede tardar entre 20 y 60 segundos)...
echo.

set /a tries=0
:wait_docker
    set /a tries+=1
    if %tries% gtr 40 (
        echo.
        echo Docker no ha arrancado en 80 segundos.
        echo Asegurate de que el icono de Docker en la barra
        echo de tareas este en verde y vuelve a intentarlo.
        pause
        exit /b 1
    )
    timeout /t 2 /nobreak >nul
    docker version >nul 2>&1
    if %errorlevel% equ 0 goto docker_ready
    <nul set /p =.
    goto wait_docker

:docker_ready
echo.
echo        Docker Engine listo.

:: ── Arrancar contenedores ────────────────────────────────────────────────────
:start_containers
echo.
echo [2/6] Arrancando servicios (base de datos, cache, almacenamiento, API)...
echo        La primera vez puede tardar 2-3 minutos (descarga de imagenes).
echo.
cd /d "%BACKEND_DIR%"
docker-compose up -d
if %errorlevel% neq 0 (
    echo.
    echo ERROR al arrancar los contenedores.
    echo Revisa el mensaje de arriba para mas detalles.
    pause
    exit /b 1
)
echo.
echo        Servicios arrancados.

:: ── Esperar a que la API este lista ──────────────────────────────────────────
echo.
echo [3/6] Esperando a que la API este lista en el puerto 8000...

set /a tries=0
:wait_api
    set /a tries+=1
    if %tries% gtr 90 (
        echo.
        echo La API no ha respondido en 3 minutos.
        echo Comprueba los logs con:
        echo    docker-compose logs api
        echo.
        echo Abriendo logs automaticamente...
        start cmd /k "cd /d \"%BACKEND_DIR%\" && docker-compose logs --tail=50 api"
        pause
        exit /b 1
    )
    timeout /t 2 /nobreak >nul
    curl -s -f http://localhost:8000/health >nul 2>&1
    if %errorlevel% equ 0 goto api_ready
    powershell -Command "try{Invoke-WebRequest -Uri 'http://localhost:8000/health' -UseBasicParsing -TimeoutSec 2|Out-Null;exit 0}catch{exit 1}" >nul 2>&1
    if %errorlevel% equ 0 goto api_ready
    <nul set /p =.
    goto wait_api

:api_ready
echo.
echo        API lista.

:: ── Tests de consistencia de esquema ─────────────────────────────────────────
echo.
echo [4/6] Verificando consistencia del esquema (tests internos)...
docker-compose exec -T api python -m pytest tests/consistency/ -q --no-header 2>nul
if %errorlevel% neq 0 (
    echo.
    echo AVISO: Los tests de consistencia han detectado problemas.
    echo Revisa el detalle arriba. Continuando de todas formas...
    echo.
)

:: ── Aplicar migraciones ───────────────────────────────────────────────────────
echo.
echo [5/6] Aplicando migraciones de base de datos...
docker-compose exec -T api alembic upgrade head
echo        Base de datos OK.

:: ── Abrir navegador ──────────────────────────────────────────────────────────
echo.
echo [6/6] Abriendo navegador...
timeout /t 2 /nobreak >nul
start "" "http://localhost:8000/docs"

echo.
echo ============================================
echo   Salvi Studio esta en marcha:
echo.
echo   API Docs:  http://localhost:8000/docs
echo   ReDoc:     http://localhost:8000/redoc
echo   MinIO:     http://localhost:9001
echo.
echo   Para parar:  docker-compose down
echo   Para logs:   docker-compose logs -f api
echo ============================================
echo.
pause
