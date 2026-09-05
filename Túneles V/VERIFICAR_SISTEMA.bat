@echo off
REM Script de verificación del sistema SalviLux
echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║  VERIFICACIÓN DEL SISTEMA SALVILUX v2.0                       ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

REM Cambiar a la carpeta del proyecto
cd /d "%~dp0"

echo Activando entorno virtual...
call venv\Scripts\activate.bat

echo.
echo ════════════════════════════════════════════════════════════════
echo 1. VERIFICANDO ARCHIVOS DEL PROYECTO
echo ════════════════════════════════════════════════════════════════
echo.

if exist test_app.py (echo ✓ test_app.py) else (echo ✗ test_app.py FALTA)
if exist photometry.py (echo ✓ photometry.py) else (echo ✗ photometry.py FALTA)
if exist visualization.py (echo ✓ visualization.py) else (echo ✗ visualization.py FALTA)
if exist ldt_reader.py (echo ✓ ldt_reader.py) else (echo ✗ ldt_reader.py FALTA)
if exist templates\index.html (echo ✓ templates\index.html) else (echo ✗ templates\index.html FALTA)

echo.
echo ════════════════════════════════════════════════════════════════
echo 2. VERIFICANDO ZIP DE LUMINARIAS
echo ════════════════════════════════════════════════════════════════
echo.

python << 'PYTHON_END'
import os
import zipfile

zip_path = "assets/LDTs_luminarias.zip"

if os.path.exists(zip_path):
    print(f"✓ ZIP encontrado: {zip_path}")

    with zipfile.ZipFile(zip_path, 'r') as z:
        archivos = z.namelist()
        ldts = [f for f in archivos if f.endswith('.ldt')]
        print(f"✓ Total archivos en ZIP: {len(archivos)}")
        print(f"✓ Archivos .ldt: {len(ldts)}")

        if len(ldts) > 0:
            print(f"\n  Primeros 5 .ldt:")
            for ldt in ldts[:5]:
                print(f"    • {ldt}")
else:
    print(f"✗ ZIP no encontrado: {zip_path}")

PYTHON_END

echo.
echo ════════════════════════════════════════════════════════════════
echo 3. VERIFICANDO MÓDULOS PYTHON
echo ════════════════════════════════════════════════════════════════
echo.

python << 'PYTHON_END'
print("\nVerificando imports...")

try:
    import flask
    print("✓ Flask instalado")
except:
    print("✗ Flask NO instalado")

try:
    import openpyxl
    print("✓ openpyxl instalado")
except:
    print("✗ openpyxl NO instalado")

try:
    import reportlab
    print("✓ reportlab instalado")
except:
    print("✗ reportlab NO instalado")

try:
    import matplotlib
    print("✓ matplotlib instalado")
except:
    print("✗ matplotlib NO instalado")

try:
    import numpy
    print("✓ numpy instalado")
except:
    print("✗ numpy NO instalado")

try:
    from ldt_reader import obtener_lista_luminarias_json
    print("✓ ldt_reader.py funciona")
except Exception as e:
    print(f"✗ ldt_reader.py error: {e}")

try:
    from photometry import calcular_fotometria
    print("✓ photometry.py funciona")
except Exception as e:
    print(f"✗ photometry.py error: {e}")

try:
    from visualization import generar_graficos_isocurvas
    print("✓ visualization.py funciona")
except Exception as e:
    print(f"✗ visualization.py error: {e}")

PYTHON_END

echo.
echo ════════════════════════════════════════════════════════════════
echo 4. CARGANDO LDTs
echo ════════════════════════════════════════════════════════════════
echo.

python << 'PYTHON_END'
import sys
sys.path.insert(0, '.')
from ldt_reader import obtener_lista_luminarias_json

resultado = obtener_lista_luminarias_json("assets/LDTs_luminarias.zip")

print(f"\nEsquema de respuesta API:")
print(f"  'success': {resultado['success']}")
print(f"  'total': {resultado['total']} luminarias")
print(f"  'luminarias': array de {len(resultado['luminarias'])} items")

if len(resultado['luminarias']) > 0:
    print(f"\nPrimer item:")
    item = resultado['luminarias'][0]
    for key, val in item.items():
        print(f"  '{key}': {val}")

PYTHON_END

echo.
echo ════════════════════════════════════════════════════════════════
echo ✅ VERIFICACIÓN COMPLETADA
echo ════════════════════════════════════════════════════════════════
echo.
echo Próximos pasos:
echo  1. TEST_APP.bat para iniciar el servidor
echo  2. http://localhost:5000 en tu navegador
echo  3. Sigue instrucciones en PRUEBA_AHORA.txt
echo.
pause
