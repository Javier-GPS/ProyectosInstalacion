@echo off
cd /d "%~dp0"
title SALVI Solar – React Dev

echo ============================================================
echo  SALVI Solar – Modo React (Vite + Flask)
echo ============================================================
echo.

:: 1. Install Python dependencies
echo [1/3] Instalando dependencias Python...
python -m pip install Flask flask-cors astral requests python-dotenv openpyxl python-docx --quiet --no-warn-script-location

:: 2. Install npm packages
echo [2/3] Instalando dependencias npm...
cd frontend
:: Remove node_modules if vite binary is missing (failed previous install)
if not exist node_modules\.bin\vite (
    if exist node_modules rmdir /s /q node_modules
    call npm install --legacy-peer-deps
) else (
    echo    node_modules ya existe y es valido, omitiendo.
)
cd ..

:: 3. Start Flask API in background (port 5001)
echo [3/3] Iniciando API Flask en puerto 5001...
start "SALVI Solar API" /min cmd /c "python api_server.py"

:: 4. Start Vite dev server in background
echo.
echo Iniciando Vite dev server...
start "SALVI Solar Dev" /min cmd /c "cd /d %~dp0frontend && node_modules\.bin\vite"

:: 5. Wait for Vite to be ready, then open browser
echo Esperando que arranque Vite...
timeout /t 4 /nobreak >nul

echo Abriendo http://localhost:5173 ...
start "" "http://localhost:5173"

echo.
echo ============================================================
echo  Servidores activos:
echo    API Flask  →  http://localhost:5001
echo    App React  →  http://localhost:5173
echo.
echo  Cierra las ventanas minimizadas para detener los servidores.
echo ============================================================
echo.
pause
