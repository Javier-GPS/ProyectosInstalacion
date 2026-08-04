@echo off
REM Script para instalar reportlab y actualizar dependencias

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║  Instalando ReportLab para generación de PDF                  ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

REM Activar virtual environment
call venv\Scripts\activate.bat

REM Instalar reportlab
echo [1/3] Instalando ReportLab...
pip install reportlab --break-system-packages

REM Instalar openpyxl si no está
echo [2/3] Verificando openpyxl...
pip install openpyxl --break-system-packages

REM Instalar Flask si no está
echo [3/3] Verificando Flask...
pip install flask --break-system-packages

echo.
echo ✓ Todas las librerías han sido instaladas correctamente
echo.
pause
