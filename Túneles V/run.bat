@echo off
REM ═══════════════════════════════════════════════════════════════════════════
REM Script para ejecutar la Aplicación de Cálculo Fotométrico
REM ═══════════════════════════════════════════════════════════════════════════

setlocal enabledelayedexpansion

REM Obtener la ruta del directorio actual
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

REM Colores ANSI (requiere Windows 10+)
REM Para versiones antiguas, se ignoran los códigos ANSI

echo.
echo ╔═══════════════════════════════════════════════════════════════════════╗
echo ║                                                                       ║
echo ║  Cálculo Fotométrico - Aplicación Flask                             ║
echo ║  v1.0                                                                 ║
echo ║                                                                       ║
echo ╚═══════════════════════════════════════════════════════════════════════╝
echo.

REM Verificar si Python está instalado
echo [1/4] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ❌ ERROR: Python no está instalado o no está en PATH
    echo.
    echo Por favor:
    echo 1. Instala Python desde https://www.python.org/downloads/
    echo 2. Marca la opción "Add Python to PATH" durante la instalación
    echo 3. Reinicia este script
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set "PYTHON_VERSION=%%i"
echo ✓ %PYTHON_VERSION% encontrado

REM Verificar si existe el entorno virtual
echo.
echo [2/4] Verificando entorno virtual...
if exist "venv\Scripts\activate.bat" (
    echo ✓ Entorno virtual encontrado
    call venv\Scripts\activate.bat
) else (
    echo ⚠ Entorno virtual no encontrado. Creando...
    python -m venv venv
    echo ✓ Entorno virtual creado
    call venv\Scripts\activate.bat
)

REM Verificar e instalar dependencias
echo.
echo [3/4] Verificando dependencias...
python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo ⚠ Dependencias no encontradas. Instalando...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ❌ Error al instalar dependencias
        echo Por favor, ejecuta manualmente:
        echo   pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
    echo ✓ Dependencias instaladas
) else (
    echo ✓ Dependencias ya están instaladas
)

REM Verificar archivos críticos
echo.
echo [4/4] Verificando archivos del proyecto...
setlocal enabledelayedexpansion
set "missing_files=0"

if not exist "app.py" (
    echo ❌ Falta: app.py
    set "missing_files=1"
) else (
    echo ✓ app.py encontrado
)

if not exist "templates\index.html" (
    echo ❌ Falta: templates\index.html
    set "missing_files=1"
) else (
    echo ✓ templates\index.html encontrado
)

if not exist "modules\validators.py" (
    echo ❌ Falta: modules\validators.py
    set "missing_files=1"
) else (
    echo ✓ modules\validators.py encontrado
)

if not exist "assets\plantilla_app_salvilux.xlsx" (
    echo ⚠ Advertencia: assets\plantilla_app_salvilux.xlsx no encontrado
) else (
    echo ✓ assets\plantilla_app_salvilux.xlsx encontrado
)

if !missing_files! equ 1 (
    echo.
    echo ❌ Faltan archivos críticos del proyecto
    echo Asegúrate de estar en la carpeta correcta del proyecto
    echo.
    pause
    exit /b 1
)

REM Todo está bien, ejecutar la aplicación
echo.
echo ═══════════════════════════════════════════════════════════════════════════
echo.
echo ✅ Verificación completada. Iniciando servidor Flask...
echo.
echo 🚀 La aplicación estará disponible en:
echo.
echo    http://localhost:5000
echo.
echo Presiona Ctrl+C para detener el servidor
echo.
echo ═══════════════════════════════════════════════════════════════════════════
echo.

REM Ejecutar la aplicación Flask
python app.py

REM Si la aplicación se cierra, mostrar mensaje
echo.
echo ⚠ La aplicación se ha cerrado
echo.
pause
