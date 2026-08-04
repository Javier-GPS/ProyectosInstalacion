@echo off
setlocal EnableExtensions
title SALVI Road LDT Designer - Arranque

set "BASE_DIR=%~dp0"
set "PROJECT_DIR=%BASE_DIR%road_ldt_designer"
set "ENGINE_URL=http://127.0.0.1:5050"
set "APP_URL=https://salvi-road-ldt-designer.salvi-lighti-7827.chatgpt.site/"

echo.
echo ============================================================
echo   SALVI STUDIO - ROAD LDT DESIGNER
echo ============================================================
echo.

if not exist "%PROJECT_DIR%\api.py" (
  echo [ERROR] No se encuentra el motor:
  echo         %PROJECT_DIR%\api.py
  goto :error
)

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python no esta instalado o no esta disponible en PATH.
  goto :error
)

echo [1/3] Comprobando dependencias del motor...
python -c "import flask, numpy" >nul 2>&1
if errorlevel 1 (
  echo       Instalando dependencias Python...
  python -m pip install -r "%PROJECT_DIR%\requirements.txt"
  if errorlevel 1 goto :python_error
)

echo [2/3] Iniciando motor fotometrico...
powershell -NoProfile -Command "try { $r=Invoke-RestMethod -Uri '%ENGINE_URL%/api/health' -TimeoutSec 2; if($r.engine -eq 'SALVI Road LDT Designer'){exit 0}else{exit 1} } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -Command "if(Get-NetTCPConnection -LocalPort 5050 -State Listen -ErrorAction SilentlyContinue){exit 0}else{exit 1}" >nul 2>&1
  if not errorlevel 1 (
    echo [ERROR] El puerto 5050 esta ocupado por otra aplicacion.
    goto :error
  )
  start "SALVI Road LDT - Motor" /min cmd /k "cd /d ""%BASE_DIR%"" && python -m road_ldt_designer.api"
)

for /L %%I in (1,1,60) do (
  powershell -NoProfile -Command "try { $r=Invoke-RestMethod -Uri '%ENGINE_URL%/api/health' -TimeoutSec 2; if($r.status -eq 'ok'){exit 0}else{exit 1} } catch { exit 1 }" >nul 2>&1
  if not errorlevel 1 goto :engine_ready
  ping -n 2 127.0.0.1 >nul
)
echo [ERROR] El motor no ha respondido despues de 60 segundos.
goto :error

:engine_ready
echo       Motor disponible en %ENGINE_URL%
echo [3/3] Abriendo la aplicacion publicada...
echo.
echo Aplicacion preparada. Abriendo %APP_URL%
start "" "%APP_URL%"
echo.
echo Puedes cerrar esta ventana. Manten abierta la ventana minimizada
echo "SALVI Road LDT - Motor" mientras utilices la aplicacion.
ping -n 4 127.0.0.1 >nul
exit /b 0

:python_error
echo [ERROR] No se han podido instalar las dependencias Python.
goto :error

:error
echo.
echo El arranque no se ha completado.
echo Revisa el mensaje anterior y pulsa una tecla para cerrar.
pause >nul
exit /b 1
