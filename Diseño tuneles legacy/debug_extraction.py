#!/usr/bin/env python
"""
Debug de la extracción del ZIP
"""

import os
import zipfile

zip_path = 'assets/LDTs_luminarias.zip'

print("\nAnalizando contenido del ZIP:")
with zipfile.ZipFile(zip_path, 'r') as z:
    archivos = z.namelist()

    print(f"Total de archivos: {len(archivos)}")
    print(f"\nPrimeros 5 archivos en el ZIP:")

    for archivo in archivos[:5]:
        print(f"\n  archivo original: '{archivo}'")

        # Método 1: splitext
        sin_ext_1 = os.path.splitext(archivo)[0]
        print(f"  método 1 (splitext): '{sin_ext_1}'")

        # Método 2: rsplit
        if '.' in archivo:
            sin_ext_2 = archivo.rsplit('.', 1)[0]
        else:
            sin_ext_2 = archivo
        print(f"  método 2 (rsplit):   '{sin_ext_2}'")

        # Extraer filename solo
        nombre_solo = archivo.split('/')[-1]
        print(f"  nombre solo: '{nombre_solo}'")

        # Chequear si contiene '/'
        tiene_slash = '/' in archivo
        print(f"  tiene '/': {tiene_slash}")
