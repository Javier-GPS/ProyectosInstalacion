#!/usr/bin/env python
"""
Script de diagnóstico para verificar que los datos de luminarias se están generando correctamente
"""

import os
import json
from ldt_reader import obtener_lista_luminarias_json

# Ruta del ZIP
ASSETS_FOLDER = os.path.join(os.path.dirname(__file__), 'assets')
zip_path = os.path.join(ASSETS_FOLDER, 'LDTs_luminarias.zip')

print("\n" + "="*80)
print("DIAGNÓSTICO DEL DROPDOWN DE LUMINARIAS")
print("="*80)

print(f"\n1. VERIFICAR ARCHIVO ZIP")
print(f"   Ruta: {zip_path}")
print(f"   Existe: {os.path.exists(zip_path)}")

if not os.path.exists(zip_path):
    print("\n❌ ERROR: No se encontró el archivo ZIP")
    exit(1)

print(f"\n2. CARGAR DATOS DE LUMINARIAS")
resultado = obtener_lista_luminarias_json(zip_path)

print(f"\n3. RESULTADO DE obtener_lista_luminarias_json():")
print(f"   - success: {resultado.get('success')}")
print(f"   - total: {resultado.get('total')}")
print(f"   - error: {resultado.get('error', 'Sin error')}")

if not resultado.get('success'):
    print("\n❌ ERROR: No se pudieron cargar los LDTs")
    exit(1)

luminarias = resultado.get('luminarias', [])

if not luminarias:
    print("\n❌ ERROR: No hay luminarias en la lista")
    exit(1)

print(f"\n4. PRIMERAS 5 LUMINARIAS:")
for i, lum in enumerate(luminarias[:5]):
    print(f"\n   Luminaria {i+1}:")
    print(f"     - id: {lum.get('id')}")
    print(f"     - label: {lum.get('label')}")
    print(f"     - flujo: {lum.get('flujo')}")
    print(f"     - nombre: {lum.get('nombre')}")
    print(f"     - fabricante: {lum.get('fabricante')}")

print(f"\n5. VERIFICACIÓN DE LABEL (lo que aparece en dropdown):")
print(f"\n   Esperado: 'CLAP_M_C42_...' o 'KRONOS_42C_...' (nombre del archivo LDT)")
print(f"   Actual en los primeros 5:")

for i, lum in enumerate(luminarias[:5]):
    label = lum.get('label', '???')
    print(f"     {i+1}. {label}")

# Buscar cualquier "SALVI" en los labels
salvi_count = sum(1 for lum in luminarias if 'SALVI' in lum.get('label', '').upper())

print(f"\n6. CONTEO DE 'SALVI' EN LABELS:")
print(f"   Luminarias con 'SALVI' en label: {salvi_count}")

if salvi_count > 0:
    print(f"\n   ❌ PROBLEMA: Hay {salvi_count} luminarias que todavía muestran 'SALVI'")
    print(f"   Ejemplos:")
    for lum in luminarias:
        if 'SALVI' in lum.get('label', '').upper():
            print(f"     - {lum.get('label')}")
else:
    print(f"\n   ✓ OK: Ninguna luminaria tiene 'SALVI' en el label")

# Exportar el JSON para inspección
output_file = 'luminarias_debug.json'
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(resultado, f, indent=2, ensure_ascii=False)

print(f"\n7. JSON COMPLETO EXPORTADO A: {output_file}")

print("\n" + "="*80)
print("FIN DEL DIAGNÓSTICO")
print("="*80 + "\n")
