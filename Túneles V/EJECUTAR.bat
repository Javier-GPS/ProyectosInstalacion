@echo off
REM ============================================================
REM EJECUTAR - SalviLux v1.0
REM Script mejorado para ejecutar la aplicación
REM ============================================================

setlocal enabledelayedexpansion

REM Obtener la ruta del directorio actual
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

cls
echo.
echo ============================================================
echo        SalviLux - Cálculo Fotométrico v1.0
echo ============================================================
echo.
echo Preparando la aplicación...
echo.

REM Verificar Python
echo [PASO 1/4] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Python no encontrado
    echo.
    echo Descargar desde: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)
python --version
echo.

REM Crear/Activar entorno virtual
echo [PASO 2/4] Entorno virtual...
if not exist "venv\" (
    echo Creando entorno virtual...
    python -m venv venv
)
call venv\Scripts\activate.bat
echo OK
echo.

REM Actualizar pip
echo [PASO 3/4] Actualizando pip...
python -m pip install --upgrade pip --quiet
echo OK
echo.

REM Instalar dependencias
echo [PASO 4/4] Instalando dependencias...
pip install --quiet Flask==2.3.3 openpyxl==3.1.2 pandas==2.0.3 Werkzeug==2.3.7 python-dotenv==1.0.0
if errorlevel 1 (
    echo ERROR durante la instalación
    echo.
    echo Intenta instalar manualmente:
    echo   pip install Flask==2.3.3 openpyxl==3.1.2 pandas==2.0.3 Werkzeug==2.3.7 python-dotenv==1.0.0
    echo.
    pause
    exit /b 1
)
echo OK
echo.

REM Ejecutar la aplicación
cls
echo ============================================================
echo        SalviLux - INICIANDO SERVIDOR
echo ============================================================
echo.
echo ABRE EN TU NAVEGADOR:
echo.
echo     http://localhost:5000
echo.
echo PARA DETENER: Presiona Ctrl+C en esta ventana
echo.
echo ============================================================
echo.

python app.py

REM Si hay error, mostrar
if errorlevel 1 (
    echo.
    echo ERROR al ejecutar app.py
    echo.
)

pause
