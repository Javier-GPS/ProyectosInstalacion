@echo off
REM ============================================================
REM INSTALAR - SalviLux v1.0
REM Script para instalar dependencias correctamente
REM ============================================================

setlocal enabledelayedexpansion

REM Obtener la ruta del directorio actual
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

cls
echo.
echo ============================================================
echo   SalviLux - INSTALACION DE DEPENDENCIAS
echo ============================================================
echo.

REM Verificar Python
echo [1/6] Verificando Python...
python --version
if errorlevel 1 (
    echo ERROR: Python no encontrado
    pause
    exit /b 1
)
echo.

REM Crear entorno virtual
echo [2/6] Creando entorno virtual...
if exist "venv\" (
    echo Eliminando entorno anterior...
    rmdir /s /q venv
)
python -m venv venv
echo.

REM Activar entorno
echo [3/6] Activando entorno virtual...
call venv\Scripts\activate.bat
echo.

REM Actualizar pip y setuptools
echo [4/6] Actualizando pip y setuptools...
python -m pip install --upgrade pip setuptools wheel
echo.

REM Instalar dependencias una por una
echo [5/6] Instalando dependencias...
echo   - Flask...
pip install Flask==2.3.3
echo   - openpyxl...
pip install openpyxl==3.1.2
echo   - pandas...
pip install pandas==2.0.3
echo   - Werkzeug...
pip install Werkzeug==2.3.7
echo   - python-dotenv...
pip install python-dotenv==1.0.0
echo.

REM Verificar instalacion
echo [6/6] Verificando instalacion...
python -c "import flask; import openpyxl; import pandas; print('OK - Todas las dependencias instaladas correctamente')"
if errorlevel 1 (
    echo ERROR: No se pudieron instalar todas las dependencias
    pause
    exit /b 1
)

cls
echo.
echo ============================================================
echo   INSTALACION COMPLETADA
echo ============================================================
echo.
echo Ahora puedes ejecutar:
echo   - EJECUTAR.bat
echo   o
echo   - python app.py
echo.
echo La aplicacion estara disponible en:
echo   http://localhost:5000
echo.
pause
