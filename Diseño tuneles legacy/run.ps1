# ═══════════════════════════════════════════════════════════════════════════
# Script PowerShell para ejecutar la Aplicación de Cálculo Fotométrico
# ═══════════════════════════════════════════════════════════════════════════

# Función para mostrar mensajes coloreados
function Write-Status {
    param(
        [string]$Message,
        [string]$Type = "Info"
    )

    $colors = @{
        "Success" = "Green"
        "Error" = "Red"
        "Warning" = "Yellow"
        "Info" = "Cyan"
    }

    $prefix = @{
        "Success" = "✓"
        "Error" = "✗"
        "Warning" = "⚠"
        "Info" = "ℹ"
    }

    $color = $colors[$Type]
    $icon = $prefix[$Type]

    Write-Host "$icon $Message" -ForegroundColor $color
}

# Banner
Write-Host ""
Write-Host "╔═══════════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                                                                       ║" -ForegroundColor Cyan
Write-Host "║  Cálculo Fotométrico - Aplicación Flask                             ║" -ForegroundColor Cyan
Write-Host "║  v1.0                                                                 ║" -ForegroundColor Cyan
Write-Host "║                                                                       ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Obtener ruta del script
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Step 1: Verificar Python
Write-Host "[1/4] Verificando Python..." -ForegroundColor White
try {
    $pythonVersion = python --version 2>&1
    Write-Status "Python encontrado: $pythonVersion" "Success"
} catch {
    Write-Status "Python no está instalado o no está en PATH" "Error"
    Write-Host ""
    Write-Host "Por favor:"
    Write-Host "1. Instala Python desde https://www.python.org/downloads/"
    Write-Host "2. Marca la opción 'Add Python to PATH' durante la instalación"
    Write-Host "3. Reinicia PowerShell y ejecuta este script nuevamente"
    Write-Host ""
    Read-Host "Presiona Enter para salir"
    exit 1
}

# Step 2: Verificar/Crear entorno virtual
Write-Host ""
Write-Host "[2/4] Verificando entorno virtual..." -ForegroundColor White
if (Test-Path "venv\Scripts\Activate.ps1") {
    Write-Status "Entorno virtual encontrado" "Success"
    & "venv\Scripts\Activate.ps1"
} else {
    Write-Status "Creando entorno virtual (esto puede tomar un minuto)..." "Warning"
    python -m venv venv
    & "venv\Scripts\Activate.ps1"
    Write-Status "Entorno virtual creado" "Success"
}

# Step 3: Verificar/Instalar dependencias
Write-Host ""
Write-Host "[3/4] Verificando dependencias..." -ForegroundColor White

$dependenciesInstalled = $false
try {
    python -c "import flask, openpyxl, pandas" -ErrorAction Stop
    $dependenciesInstalled = $true
    Write-Status "Dependencias ya están instaladas" "Success"
} catch {
    Write-Status "Instalando dependencias..." "Warning"
    pip install -r requirements.txt --quiet
    Write-Status "Dependencias instaladas" "Success"
}

# Step 4: Verificar archivos críticos
Write-Host ""
Write-Host "[4/4] Verificando archivos del proyecto..." -ForegroundColor White

$criticalFiles = @(
    "app.py",
    "config.py",
    "modules\validators.py",
    "modules\excel_handler.py",
    "templates\index.html",
    "requirements.txt"
)

$missingFiles = @()

foreach ($file in $criticalFiles) {
    if (Test-Path $file) {
        Write-Status "$file encontrado" "Success"
    } else {
        Write-Status "$file NO ENCONTRADO" "Error"
        $missingFiles += $file
    }
}

# Archivos opcionales
$optionalFiles = @(
    "assets\plantilla_app_dialux.xlsx",
    "assets\LDTs_luminarias.zip"
)

foreach ($file in $optionalFiles) {
    if (Test-Path $file) {
        Write-Status "$file encontrado" "Success"
    } else {
        Write-Status "$file no encontrado (opcional)" "Warning"
    }
}

# Si faltan archivos críticos, salir
if ($missingFiles.Count -gt 0) {
    Write-Host ""
    Write-Status "Faltan archivos críticos del proyecto" "Error"
    Write-Host "Asegúrate de estar en la carpeta correcta del proyecto"
    Write-Host ""
    Read-Host "Presiona Enter para salir"
    exit 1
}

# Ejecutar la aplicación
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Status "Verificación completada. Iniciando servidor Flask..." "Success"
Write-Host ""
Write-Host "🚀 La aplicación estará disponible en:" -ForegroundColor Yellow
Write-Host ""
Write-Host "   http://localhost:5000" -ForegroundColor Cyan
Write-Host ""
Write-Host "📝 Presiona Ctrl+C para detener el servidor" -ForegroundColor Yellow
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""

# Ejecutar Flask
python app.py

# Mensaje de cierre
Write-Host ""
Write-Host "⚠ La aplicación se ha cerrado" -ForegroundColor Yellow
Write-Host ""
Read-Host "Presiona Enter para salir"
