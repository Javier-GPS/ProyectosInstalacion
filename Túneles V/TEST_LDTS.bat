@echo off
REM Script para probar que ldt_reader funciona

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║  Test de LDT Reader - Verificar carga de luminarias           ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

REM Cambiar a la carpeta del proyecto
cd /d "%~dp0"

echo Carpeta actual:
cd

echo.
echo Activando virtual environment...
call venv\Scripts\activate.bat

echo.
echo Ejecutando test...
python test_ldts.py

echo.
pause
