@echo off
setlocal

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "PYTHON=%LocalAppData%\Programs\Python\Python312\python.exe"

if not exist "%PYTHON%" set "PYTHON=python"

if not exist "%BACKEND%\luminaire_optimizer\__main__.py" (
    echo No se encuentra el backend en:
    echo %BACKEND%
    pause
    exit /b 1
)

if not exist "%FRONTEND%\package.json" (
    echo No se encuentra el frontend en:
    echo %FRONTEND%
    pause
    exit /b 1
)

echo Iniciando SALVI Luminaria Optimizer...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8760 .*LISTENING"') do taskkill /F /PID %%P >nul 2>&1
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":5176 .*LISTENING"') do taskkill /F /PID %%P >nul 2>&1
start "SALVI Backend - puerto 8760" /D "%BACKEND%" "%ComSpec%" /d /k ""%PYTHON%" -m luminaire_optimizer"
start "SALVI Frontend - puerto 5176" /D "%FRONTEND%" "%ComSpec%" /d /k "call npm.cmd run dev"

echo Esperando al frontend...
for /l %%I in (1,1,15) do (
    powershell -NoProfile -Command "$r = try { Invoke-WebRequest -Uri 'http://localhost:5176' -UseBasicParsing -TimeoutSec 1 } catch { $null }; if ($r) { exit 0 } else { exit 1 }" >nul 2>&1
    if not errorlevel 1 goto :frontend_ready
    timeout /t 1 /nobreak >nul
)
echo El frontend no respondio en 15 segundos. Revisa la ventana "SALVI Frontend - puerto 5176".
goto :finish

:frontend_ready
start "" "http://localhost:5176"

echo.
echo Backend:  http://127.0.0.1:8760
echo Frontend: http://localhost:5176
echo Puedes cerrar esta ventana.

:finish
endlocal
