@echo off
REM ============================================================
REM SETUP - SalviLux
REM Script de instalacion ultra-simplificado
REM ============================================================

cd /d "%~dp0"

echo.
echo ============================================================
echo SalviLux - INSTALACION
echo ============================================================
echo.

REM Crear venv
if not exist "venv" python -m venv venv

REM Activar
call venv\Scripts\activate.bat

REM Upgrade pip
echo Actualizando pip...
python -m pip install --upgrade pip

REM Instalar con --prefer-binary para evitar compilacion
echo.
echo Instalando Flask...
pip install --prefer-binary --no-cache-dir Flask

echo Instalando openpyxl...
pip install --prefer-binary --no-cache-dir openpyxl

echo Instalando pandas...
pip install --prefer-binary --no-cache-dir pandas

echo Instalando Werkzeug...
pip install --prefer-binary --no-cache-dir Werkzeug

echo Instalando python-dotenv...
pip install --prefer-binary --no-cache-dir python-dotenv

echo Instalando anthropic (asistente IA de tuneles)...
pip install --prefer-binary --no-cache-dir anthropic

echo.
echo ============================================================
echo INSTALACION COMPLETADA
echo ============================================================
echo.
echo Ahora ejecuta: CORRER.bat
echo.

pause
