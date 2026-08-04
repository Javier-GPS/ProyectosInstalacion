@echo off
REM ============================================================
REM INSTALAR_FACIL - SalviLux v1.0
REM Script simplificado que evita problemas de compilacion
REM ============================================================

setlocal enabledelayedexpansion

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

cls
echo.
echo ============================================================
echo   SalviLux - INSTALACION (Versión mejorada)
echo ============================================================
echo.

REM Verificar Python
echo [1/5] Verificando Python...
python --version
if errorlevel 1 (
    echo ERROR: Python no encontrado
    pause
    exit /b 1
)
echo OK
echo.

REM Crear entorno virtual limpio
echo [2/5] Preparando entorno...
if exist "venv\" (
    echo Limpiando entorno anterior...
    rmdir /s /q venv >nul 2>&1
)
python -m venv venv
call venv\Scripts\activate.bat
echo OK
echo.

REM Actualizar herramientas basicas
echo [3/5] Actualizando herramientas...
python -m pip install --upgrade pip setuptools wheel
echo OK
echo.

REM Instalar con configuracion optimizada
echo [4/5] Instalando paquetes...
pip install --prefer-binary Flask==2.3.3 openpyxl==3.1.2 Werkzeug==2.3.7 python-dotenv==1.0.0
pip install --prefer-binary pandas==2.0.3
echo OK
echo.

REM Verificar
echo [5/5] Verificando instalacion...
python -c "import flask, openpyxl, pandas, dotenv; print('Verificacion OK')"
if errorlevel 1 (
    echo.
    echo ⚠ Algunos paquetes no se instalaron correctamente
    echo Intenta de nuevo o contacta al soporte
    pause
    exit /b 1
)

cls
echo.
echo ============================================================
echo   ✓ INSTALACION COMPLETADA
echo ============================================================
echo.
echo Ahora ejecuta:
echo   CORRER.bat
echo.
echo O si prefieres la linea de comandos:
echo   python app.py
echo.
pause
