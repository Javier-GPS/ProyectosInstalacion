@echo off
REM ============================================================
REM INSTALAR_RAPIDO - SalviLux
REM Instalacion directa usando requirements.txt
REM ============================================================

setlocal
cd /d "%~dp0"

echo.
echo ============================================================
echo SalviLux - INSTALACION RAPIDA
echo ============================================================
echo.

REM Crear entorno
if not exist "venv" (
    echo Creando entorno virtual...
    python -m venv venv
)

REM Activar
call venv\Scripts\activate.bat

REM Upgrade pip primero
echo.
echo Actualizando pip...
python -m pip install --upgrade pip setuptools wheel --quiet

REM Instalar requirements
echo Instalando dependencias...
pip install --prefer-binary --no-cache-dir -r requirements.txt

echo.
echo ============================================================
echo LISTO - Ahora ejecuta: CORRER.bat
echo ============================================================
echo.

pause
