#!/usr/bin/env python3
"""
Script de verificación de instalación y estructura
Verifica que todos los archivos y módulos están correctamente configurados
"""

import os
import sys
from pathlib import Path

def check_file(path, description):
    """Verifica si un archivo existe"""
    if os.path.exists(path):
        size = os.path.getsize(path)
        print(f"✓ {description}: {path} ({size} bytes)")
        return True
    else:
        print(f"✗ {description}: FALTA - {path}")
        return False

def check_module(module_name, description):
    """Verifica si un módulo Python puede importarse"""
    try:
        __import__(module_name)
        print(f"✓ {description}: {module_name}")
        return True
    except ImportError as e:
        print(f"✗ {description}: {module_name} - {e}")
        return False

def main():
    print("=" * 60)
    print("VERIFICACIÓN DE INSTALACIÓN - CÁLCULO FOTOMÉTRICO")
    print("=" * 60)
    print()

    # Obtener ruta del proyecto
    project_root = os.path.dirname(os.path.abspath(__file__))
    print(f"📁 Raíz del proyecto: {project_root}")
    print()

    checks = []

    # 1. Verificar archivos Python
    print("1️⃣  Verificando archivos Python:")
    checks.append(check_file(os.path.join(project_root, 'app.py'), "Aplicación Flask"))
    checks.append(check_file(os.path.join(project_root, 'requirements.txt'), "Dependencias"))
    checks.append(check_file(os.path.join(project_root, 'modules', '__init__.py'), "Módulo __init__"))
    checks.append(check_file(os.path.join(project_root, 'modules', 'validators.py'), "Validador"))
    checks.append(check_file(os.path.join(project_root, 'modules', 'excel_handler.py'), "Manejador Excel"))
    print()

    # 2. Verificar templates
    print("2️⃣  Verificando plantillas HTML:")
    checks.append(check_file(os.path.join(project_root, 'templates', 'index.html'), "Interfaz web"))
    print()

    # 3. Verificar assets
    print("3️⃣  Verificando recursos:")
    checks.append(check_file(os.path.join(project_root, 'assets', 'plantilla_app_salvilux.xlsx'), "Plantilla Excel"))
    checks.append(check_file(os.path.join(project_root, 'assets', 'LDTs_luminarias.zip'), "Librería LDT"))
    print()

    # 4. Verificar documentación
    print("4️⃣  Verificando documentación:")
    checks.append(check_file(os.path.join(project_root, 'README.md'), "Documentación completa"))
    checks.append(check_file(os.path.join(project_root, 'QUICKSTART.md'), "Guía rápida"))
    print()

    # 5. Verificar módulos Python instalados
    print("5️⃣  Verificando dependencias Python:")
    checks.append(check_module('flask', "Flask"))
    checks.append(check_module('openpyxl', "openpyxl"))
    checks.append(check_module('werkzeug', "Werkzeug"))
    checks.append(check_module('pandas', "pandas"))
    print()

    # 6. Verificar estructura de directorios
    print("6️⃣  Verificando directorios:")
    dirs_to_check = [
        (os.path.join(project_root, 'modules'), "Módulos"),
        (os.path.join(project_root, 'templates'), "Plantillas"),
        (os.path.join(project_root, 'assets'), "Recursos"),
    ]

    for dir_path, desc in dirs_to_check:
        if os.path.isdir(dir_path):
            print(f"✓ Directorio {desc}: {dir_path}")
            checks.append(True)
        else:
            print(f"✗ Directorio {desc}: FALTA - {dir_path}")
            checks.append(False)
    print()

    # 7. Resumen
    print("=" * 60)
    total = len(checks)
    passed = sum(checks)
    failed = total - passed
    percentage = (passed / total * 100) if total > 0 else 0

    print(f"RESUMEN: {passed}/{total} verificaciones pasadas ({percentage:.1f}%)")
    print()

    if failed == 0:
        print("🟢 ¡INSTALACIÓN COMPLETADA!")
        print()
        print("Próximos pasos:")
        print("1. Ejecutar la aplicación: python app.py")
        print("2. Abrir en el navegador: http://localhost:5000")
        print("3. Ver QUICKSTART.md para instrucciones de uso")
        return 0
    else:
        print(f"🔴 ERRORES: {failed} verificaciones fallaron")
        print()
        print("Por favor, siga estos pasos:")
        print("1. Instalar dependencias: pip install -r requirements.txt")
        print("2. Verificar que all archivos están en su lugar")
        print("3. Ejecutar de nuevo este script")
        return 1

if __name__ == '__main__':
    sys.exit(main())
