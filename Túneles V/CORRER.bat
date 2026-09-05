@echo off
REM ============================================================
REM CORRER - SalviLux v1.0
REM Script para ejecutar la aplicacion (requiere dependencias ya instaladas)
REM ============================================================

setlocal enabledelayedexpansion

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

cls
echo.
echo ============================================================
echo   SalviLux - INICIANDO APLICACION
echo ============================================================
echo.

REM Activar entorno virtual si existe
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM Ejecutar Flask
echo Iniciando servidor Flask...
echo.
echo ABRE EN TU NAVEGADOR:
echo   http://localhost:5000
echo.
echo Para detener: Presiona Ctrl+C
echo.

python app.py

if errorlevel 1 (
    echo.
    echo ERROR al ejecutar la aplicacion
    echo.
    echo Si es la primera vez, ejecuta primero:
    echo   INSTALAR.bat
    echo.
)

pause
