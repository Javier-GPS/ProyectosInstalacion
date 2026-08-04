#!/usr/bin/env python
"""
Debug script para ver qué claves se están usando en el diccionario de luminarias
"""

import os
from ldt_reader import cargar_ldts_desde_zip

ASSETS_FOLDER = os.path.join(os.path.dirname(__file__), 'assets')
zip_path = os.path.join(ASSETS_FOLDER, 'LDTs_luminarias.zip')

print("\nCargando luminarias...")
reader = cargar_ldts_desde_zip(zip_path)

if reader:
    print(f"\nTotal de luminarias en diccionario: {len(reader.luminarias)}")
    print(f"\nPrimeras 10 claves del diccionario:")

    for i, (clave, info) in enumerate(list(reader.luminarias.items())[:10]):
        print(f"  {i+1}. Clave: '{clave}'")
        print(f"     nombre: {info.get('nombre', '')[:50]}")
        print(f"     fabricante: {info.get('fabricante', '')[:50]}")
        print()
