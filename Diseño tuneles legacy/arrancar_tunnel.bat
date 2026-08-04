@echo off
cd /d "%~dp0"

REM Usar siempre el interprete del entorno virtual del proyecto.
REM Esto evita que Windows lance otra instalacion de Python al abrir el BAT.
set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

cls
echo.
echo ============================================================
echo  SALVI Tunnel Engine - CIE 88:2004
echo ============================================================
echo.
echo  Iniciando servidor Flask...
echo.

REM Si ya hay un servidor activo, no crear otra instancia que compita por el puerto.
curl.exe -fsS --max-time 2 "http://127.0.0.1:5000/tunnel" > nul 2>&1
if %errorlevel%==0 goto :open_browser

REM Arrancar Flask en segundo plano (ventana separada minimizada)
start "SALVI Tunnel Engine" /min "%PYTHON_EXE%" app.py

REM Esperar hasta que Flask responda, no solo un tiempo fijo.
echo  Esperando a que el servidor este listo...
set "SERVER_READY=0"
for /L %%I in (1,1,30) do (
    curl.exe -fsS --max-time 2 "http://127.0.0.1:5000/tunnel" > nul 2>&1
    if not errorlevel 1 (
        set "SERVER_READY=1"
        goto :open_browser
    )
    timeout /t 1 /nobreak > nul
)

echo.
echo ERROR: Flask no responde en http://127.0.0.1:5000/tunnel
echo Revisa la ventana minimizada "SALVI Tunnel Engine" para ver el error.
pause
exit /b 1

:open_browser
REM Abrir el navegador
explorer.exe "http://localhost:5000/tunnel" > nul 2>&1

echo.
echo ============================================================
echo  Servidor activo en:
echo.
echo    Modulo tuneles  ->  http://localhost:5000/tunnel
echo    App principal   ->  http://localhost:5000
echo.
echo  El servidor corre en segundo plano (barra de tareas).
echo  Para detenerlo: cierra la ventana "SALVI Tunnel Engine".
echo ============================================================
echo.

REM Cerrar esta ventana de lanzamiento automaticamente
exit /b 0
