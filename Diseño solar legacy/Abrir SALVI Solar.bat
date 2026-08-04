@echo off
cd /d "%~dp0"
title SALVI Solar

echo Instalando dependencias (primera vez puede tardar)...
python -m pip install Flask flask-cors astral requests python-dotenv openpyxl --no-warn-script-location

echo.
echo Iniciando servidor SALVI Solar...
echo NO cierres esta ventana.
echo.

start "" "http://localhost:5001"

python api_server.py

echo.
echo El servidor se ha cerrado.
pause
