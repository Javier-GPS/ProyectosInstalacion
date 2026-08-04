@echo off
REM ============================================================
REM Script simplificado para ejecutar SalviLux
REM ============================================================

setlocal enabledelayedexpansion

REM Obtener la ruta del directorio actual
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

echo.
echo ============================================================
echo Cálculo Fotométrico SalviLux - Aplicación Flask v1.0
echo ============================================================
echo.

REM Verificar si Python está instalado
echo [PASO 1/3] Verificando Python...
python --version
if errorlevel 1 (
    echo.
    echo ERROR: Python no está instalado o no está en PATH
    echo.
    echo Solución:
    echo 1. Descarga Python desde https://www.python.org/downloads/
    echo 2. Durante la instalación, marca "Add Python to PATH"
    echo 3. Reinicia el script
    echo.
    pause
    exit /b 1
)

REM Crear entorno virtual si no existe
echo.
echo [PASO 2/3] Configurando entorno virtual...
if not exist "venv\" (
    echo Creando entorno virtual...
    python -m venv venv
    echo Entorno virtual creado
)

REM Activar entorno virtual
call venv\Scripts\activate.bat

REM Instalar dependencias
echo.
echo [PASO 3/3] Instalando dependencias (esto puede tomar un momento)...
pip install -r requirements.txt

echo.
echo ============================================================
echo Iniciando servidor Flask...
echo ============================================================
echo.
echo ABRE en tu navegador:
echo    http://localhost:5000
echo.
echo Para detener: Presiona Ctrl+C
echo.

REM Ejecutar la aplicación
python app.py

pause
