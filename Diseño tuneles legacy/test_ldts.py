#!/usr/bin/env python
"""
Script de prueba para verificar que ldt_reader funciona correctamente
"""

import os
import sys
from ldt_reader import cargar_ldts_desde_zip, obtener_lista_luminarias_json

# Ruta del ZIP
zip_path = os.path.join(os.path.dirname(__file__), 'assets', 'LDTs_luminarias.zip')

print("\n" + "="*70)
print("TEST LDT READER")
print("="*70)

print(f"\n1. Verificando ruta del ZIP:")
print(f"   Ruta: {zip_path}")
print(f"   Existe: {os.path.exists(zip_path)}")

if not os.path.exists(zip_path):
    print("\n❌ ERROR: ZIP no encontrado")
    sys.exit(1)

print(f"\n2. Obteniendo lista de luminarias...")
resultado = obtener_lista_luminarias_json(zip_path)

print(f"\n3. Resultado:")
print(f"   Éxito: {resultado.get('success')}")
print(f"   Total: {resultado.get('total')}")
print(f"   Error: {resultado.get('error', 'Ninguno')}")

if resultado.get('success'):
    print(f"\n4. Primeras 5 luminarias:")
    for i, lum in enumerate(resultado.get('luminarias', [])[:5]):
        print(f"\n   [{i+1}] {lum['label']}")
        print(f"       ID: {lum['id']}")
        print(f"       Flujo: {lum['flujo']} lm")
        print(f"       Nombre: {lum['nombre']}")
        print(f"       Fabricante: {lum['fabricante']}")
else:
    print(f"\n❌ ERROR: {resultado.get('error')}")

print("\n" + "="*70)
if resultado.get('success') and resultado.get('total', 0) > 0:
    print("✅ TEST EXITOSO - LDTs se cargan correctamente")
else:
    print("❌ TEST FALLIDO - Revisar errores arriba")
print("="*70 + "\n")
