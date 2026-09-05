@echo off
REM Script para instalar matplotlib y numpy para gráficos

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║  Instalando Matplotlib y NumPy para gráficas de isocurvas     ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

REM Activar virtual environment
call venv\Scripts\activate.bat

REM Instalar matplotlib (incluye numpy automáticamente)
echo [1/2] Instalando Matplotlib...
pip install matplotlib --break-system-packages

REM Verificar numpy
echo [2/2] Verificando NumPy...
pip install numpy --break-system-packages

echo.
echo ✓ Todas las librerías han sido instaladas correctamente
echo   - matplotlib: Gráficos y visualización
echo   - numpy: Operaciones numéricas
echo.
pause
