@echo off
REM ============================================================
REM TEST_APP - SalviLux
REM Versión simplificada para hacer pruebas
REM ============================================================

setlocal
cd /d "%~dp0"

echo.
echo ============================================================
echo SalviLux - TEST APP (Simplificado)
echo ============================================================
echo.

if not exist "venv" (
    echo ERROR: Carpeta venv no encontrada
    echo Ejecuta primero: SETUP.bat
    echo.
    pause
    exit /b 1
)

echo Activando entorno virtual...
call venv\Scripts\activate.bat

if errorlevel 1 (
    echo ERROR: No se pudo activar el entorno virtual
    pause
    exit /b 1
)

echo.
echo ============================================================
echo SERVIDOR TEST INICIANDO...
echo ============================================================
echo.
echo Abre en tu navegador:
echo   http://localhost:5000
echo.
echo Prueba estos endpoints:
echo   http://localhost:5000/api/test
echo   http://localhost:5000/api/debug/files
echo.
echo Llena el formulario y haz clic en CALCULAR
echo.
echo Para DETENER el servidor, presiona: Ctrl + C
echo.
echo ============================================================
echo.

REM Ejecutar test app
python test_app.py

pause
