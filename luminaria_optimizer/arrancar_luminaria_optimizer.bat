@echo off
setlocal
title SALVI Luminaria Optimizer

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
call :check_backend
if errorlevel 1 (
    for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8760 .*LISTENING"') do taskkill /F /PID %%P >nul 2>&1
    start "SALVI Backend - puerto 8760" /D "%BACKEND%" "%ComSpec%" /d /k ""%PYTHON%" -m luminaire_optimizer"
)

call :check_url "http://127.0.0.1:5176"
if errorlevel 1 (
    for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":5176 .*LISTENING"') do taskkill /F /PID %%P >nul 2>&1
    start "SALVI Frontend - puerto 5176" /D "%FRONTEND%" "%ComSpec%" /d /k "call npm.cmd run dev"
)

echo Abriendo la aplicacion en el navegador...
start "" explorer.exe "http://localhost:5176/"

echo.
echo Backend:  http://127.0.0.1:8760
echo Frontend: http://localhost:5176
echo Si la pagina tarda unos segundos, espera a que Vite termine de iniciar.
echo Puedes cerrar esta ventana.

:finish
endlocal
exit /b

:check_url
powershell -NoProfile -Command "$r = try { Invoke-WebRequest -Uri '%~1' -UseBasicParsing -TimeoutSec 2 } catch { $null }; if ($r -and $r.StatusCode -eq 200) { exit 0 } else { exit 1 }" >nul 2>&1
exit /b %errorlevel%

:check_backend
powershell -NoProfile -Command "$r = try { Invoke-WebRequest -Uri 'http://127.0.0.1:8760/api/health' -UseBasicParsing -TimeoutSec 2 } catch { $null }; if ($r -and $r.StatusCode -eq 200 -and $r.Content -match 'vision-staged-v11') { exit 0 } else { exit 1 }" >nul 2>&1
exit /b %errorlevel%
