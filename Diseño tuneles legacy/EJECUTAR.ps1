# ============================================================
# EJECUTAR - SalviLux v1.0
# Script PowerShell para ejecutar la aplicación
# ============================================================

$ErrorActionPreference = "Continue"

# Obtener directorio del script
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDir

Clear-Host

Write-Host ""
Write-Host "============================================================"
Write-Host "        SalviLux - Cálculo Fotométrico v1.0"
Write-Host "============================================================"
Write-Host ""

# Paso 1: Verificar Python
Write-Host "[PASO 1/4] Verificando Python..." -ForegroundColor Cyan
$pythonExists = $null -ne (Get-Command python -ErrorAction SilentlyContinue)

if (-not $pythonExists) {
    Write-Host ""
    Write-Host "ERROR: Python no encontrado" -ForegroundColor Red
    Write-Host ""
    Write-Host "Descargar desde: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Presiona Enter para salir"
    exit 1
}

python --version
Write-Host ""

# Paso 2: Entorno virtual
Write-Host "[PASO 2/4] Entorno virtual..." -ForegroundColor Cyan
if (-not (Test-Path "venv")) {
    Write-Host "Creando entorno virtual..."
    python -m venv venv
}

# Activar entorno virtual
& ".\venv\Scripts\Activate.ps1"
Write-Host "OK" -ForegroundColor Green
Write-Host ""

# Paso 3: Actualizar pip
Write-Host "[PASO 3/4] Actualizando pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip --quiet
Write-Host "OK" -ForegroundColor Green
Write-Host ""

# Paso 4: Instalar dependencias
Write-Host "[PASO 4/4] Instalando dependencias..." -ForegroundColor Cyan
pip install --quiet Flask==2.3.3 openpyxl==3.1.2 pandas==2.0.3 Werkzeug==2.3.7 python-dotenv==1.0.0

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR durante la instalación" -ForegroundColor Red
    Write-Host ""
    Write-Host "Intenta instalar manualmente:" -ForegroundColor Yellow
    Write-Host "  pip install Flask==2.3.3 openpyxl==3.1.2 pandas==2.0.3 Werkzeug==2.3.7 python-dotenv==1.0.0"
    Write-Host ""
    Read-Host "Presiona Enter para salir"
    exit 1
}

Write-Host "OK" -ForegroundColor Green
Write-Host ""

# Ejecutar la aplicación
Clear-Host
Write-Host "============================================================"
Write-Host "        SalviLux - INICIANDO SERVIDOR"
Write-Host "============================================================"
Write-Host ""
Write-Host "ABRE EN TU NAVEGADOR:" -ForegroundColor Green
Write-Host ""
Write-Host "     http://localhost:5000" -ForegroundColor Yellow
Write-Host ""
Write-Host "PARA DETENER: Presiona Ctrl+C en esta ventana"
Write-Host ""
Write-Host "============================================================"
Write-Host ""

python app.py

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR al ejecutar app.py" -ForegroundColor Red
    Write-Host ""
}

Read-Host "Presiona Enter para salir"
