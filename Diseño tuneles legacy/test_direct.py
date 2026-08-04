#!/usr/bin/env python
"""
Test directo del diccionario
"""

import os
import sys

# Ensure we get the freshest version
if 'ldt_reader' in sys.modules:
    del sys.modules['ldt_reader']

from ldt_reader import LDTReader

zip_path = os.path.join('assets', 'LDTs_luminarias.zip')

print("Creando LDTReader...")
reader = LDTReader(zip_path)

print("Llamando a extraer_zip_ldts()...")
luminarias_dict = reader.extraer_zip_ldts(zip_path)

print(f"\nDiccionario contiene {len(luminarias_dict)} items")
print("\nPrimeras 3 claves del diccionario:")

for i, key in enumerate(list(luminarias_dict.keys())[:3]):
    print(f"{i+1}. Clave: '{key}'")
    print(f"   Tipo de clave: {type(key)}")
    print(f"   Tiene 'Salvi/'? {'Salvi/' in key}")
    print(f"   Primer carácter: {key[0] if key else 'N/A'}")
