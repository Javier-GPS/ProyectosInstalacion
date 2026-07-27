@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

:: SALVI GIS - Lanzador

:: Detectar Python
set "PYTHON="
python --version >nul 2>&1
if not errorlevel 1 set "PYTHON=python"
if not defined PYTHON (
    python3 --version >nul 2>&1
    if not errorlevel 1 set "PYTHON=python3"
)

if not defined PYTHON (
    echo Python no encontrado. Instalalo desde https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Instalar paquetes si faltan
%PYTHON% -c "import ezdxf" >nul 2>&1
if errorlevel 1 %PYTHON% -m pip install ezdxf --quiet --no-warn-script-location >nul 2>&1

%PYTHON% -c "import openpyxl" >nul 2>&1
if errorlevel 1 %PYTHON% -m pip install openpyxl --quiet --no-warn-script-location >nul 2>&1

:: Cerrar instancias previas en puertos 8732 y 8733
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8732 " ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8733 " ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

:: Arrancar backend (minimizado, no cerrar)
start /min "SALVI Backend 8733" %PYTHON% api_server.py

:: Arrancar frontend (minimizado, no cerrar)
start /min "SALVI Frontend 8732" %PYTHON% -m http.server 8732

:: Esperar y abrir navegador
timeout /t 3 /nobreak >nul

set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe"      set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe"       set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"

if defined CHROME (
    start "" "%CHROME%" "http://localhost:8732/SALVI GIS.html"
) else (
    start "" "http://localhost:8732/SALVI GIS.html"
)
