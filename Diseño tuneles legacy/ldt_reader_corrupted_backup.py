#!/usr/bin/env python
"""
Módulo para leer y procesar archivos LDT (fotometría de luminarias)
Extrae información de archivos LDT: nombre, flujo luminoso, óptica, etc.
"""

import os
import zipfile
import re
from io import StringIO

class LDTReader:
    """Lee y procesa archivos LDT (Luminous Distribution Table)"""

    def __init__(self, ldt_path):
        """
        Inicializa con ruta al archivo LDT o ZIP de LDTs
        """
        self.ldt_path = ldt_path
        self.luminarias = {}

    def extraer_zip_ldts(self, zip_path):
        """
        Extrae informacion de todos los LDTs en un ZIP
        Busca archivos con extension .ldt, .ies, .txt o sin extension
        """
        try:
            if not os.path.exists(zip_path):
                print(f"⚠️ ZIP no encontrado: {zip_path}")
                return {}

            luminarias = {}

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Listar archivos en el ZIP
                archivos = zip_ref.namelist()
                print(f"DEBUG: Encontrados {len(archivos)} archivos en ZIP")
                print(f"DEBUG: Archivos: {archivos}")

                for archivo in archivos:
                    # Saltar directorios
                    if archivo.endswith('/'):
                        continue

                    # Obtener extensión
                    ext = os.path.splitext(archivo)[1].lower()
                    nombre_base = os.path.basename(archivo)

                    # Buscar archivos que parecen ser LDT:
                    # - .ldt, .ies (formato photometry), .txt (si contiene datos)
                    # - O archivos sin extensión con nombres típicos
                    es_ldt = (
                        ext in ['.ldt', '.ies', '.txt'] or
                        ext == '' or
                        'ldt' in nombre_base.lower() or
                        'lum' in nombre_base.lower()
                    )

                    if not es_ldt:
                        continue

                    try:
                        with zip_ref.open(archivo) as f:
                            contenido = f.read().decode('utf-8', errors='ignore')

                            # Verificar que tiene contenido y se parece a un LDT
                            if len(contenido.strip()) < 50:
                                print(f"⚠️ {nombre_base}: Archivo muy pequeño, saltando")
                                continue

                            info = self.parsear_ldt(contenido, archivo)

                            if info:
                                # Usar ruta relativa sin extensión como clave
                                # Esto mantiene la carpeta (Salvi/, LTI/, etc)
                                # IMPORTANTE: Usar el nombre del archivo ORIGINAL del ZIP para la clave
                                # porque os.path.splitext puede comportarse diferente en Windows

                                if archivo.endswith('.ldt') or archivo.endswith('.ies') or archivo.endswith('.txt'):
                                    # Remover extensión preservando las barras del ZIP
                                    ruta_relativa = archivo.rsplit('.', 1)[0]
                                else:
                                    ruta_relativa = archivo

                                # Guardar el nombre del archivo en info para luego usarlo en el dropdown
                                info['nombre_archivo'] = ruta_relativa
                                luminarias[ruta_relativa] = info
                                print(f"✓ LDT leído: {ruta_relativa} ({info.get('nombre', '')})")
                            else:
                                print(f"⚠️ {nombre_base}: No se pudo parsear")

                    except Exception as e:
                        print(f"⚠️ Error leyendo {archivo}: {str(e)}")
                        continue

            if not luminarias:
                print(f"⚠️ No se encontraron archivos LDT válidos")
            else:
                print(f"✓ Total: {len(luminarias)} luminarias cargadas")

            return luminarias

        except Exception as e:
            print(f"❌ Error extrayendo ZIP: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return {}

    def parsear_ldt(self, contenido, nombre_archivo=""):
        """
        Parsea contenido de archivo LDT
        Formato LDT (texto ASCII):
        - Líneas 1-7: Información de la luminaria
        - Línea 8: Ángulos C
        - Línea 9: Ángulos G
        - Resto: Valores de intensidad

        También soporta formatos IES y variaciones
        """
        try:
            lineas = contenido.strip().split('\n')

            if len(lineas) < 2:
                return None

            info = {
                'archivo': nombre_archivo,
                'nombre': '',
                'fabricante': '',
                'tipo': '',
                'flujo_nominal': 0,
                'intensidad_max': 0,
                'angulos_c': [],
                'angulos_g': [],
            }

            # Detectar formato IES (comienza con "IESNA")
            es_ies = contenido.strip().upper().startswith('IESNA')

            if es_ies:
                # Formato IES - extraer nombre y datos
                info['nombre'] = 'Luminaria IES'
                info['tipo'] = 'IES Format'

                # Buscar línea con "TILT=" para encontrar datos
                for i, linea in enumerate(lineas):
                    if 'TILT=' in linea.upper():
                        # Siguiente línea tiene los datos
                        if i + 1 < len(lineas):
                            try:
                                valores = lineas[i+1].split()
                                for val in valores:
                                    num = float(val)
                                    if 100 < num < 1000000:
                                        info['flujo_nominal'] = int(num)
                                        break
                            except:
                                pass
                        break
            else:
                # Formato LDT estándar
                # Línea 1: Nombre de la luminaria / Descripción
                if len(lineas) > 0:
                    info['nombre'] = lineas[0].strip()[:100]

                # Línea 2: Fabricante
                if len(lineas) > 1:
                    info['fabricante'] = lineas[1].strip()[:100]

                # Línea 3: Tipo de luminaria
                if len(lineas) > 2:
                    info['tipo'] = lineas[2].strip()[:100]

                # Búsqueda de flujo luminoso en el archivo
                # Primero intentar línea 8 (formato Salvi), luego línea 4
                try:
                    flujo_encontrado = False

                    # Intentar línea 29 (formato Salvi con flujo real)
                    if len(lineas) > 28 and not flujo_encontrado:
                        try:
                            num = float(lineas[28].strip())
                            if 10000 < num < 100000:  # Rango de flujo Salvi
                                info['flujo_nominal'] = int(num)
                                flujo_encontrado = True
                        except:
                            pass

                    # Si no, buscar en línea 4 (formato LDT estándar)
                    if len(lineas) > 3 and not flujo_encontrado:
                        valores = lineas[3].split()
                        if valores:
                            for val in valores:
                                try:
                                    num = float(val)
                                    if 100 < num < 1000000:
                                        info['flujo_nominal'] = int(num)
                                        flujo_encontrado = True
                                        break
                                except ValueError:
                                    continue

                    # Si aún no, buscar el primer número grande en todo el archivo
                    if not flujo_encontrado:
                        for linea in lineas[4:50]:
                            try:
                                num = float(linea.strip())
                                if 10000 < num < 100000:
                                    info['flujo_nominal'] = int(num)
                                    flujo_encontrado = True
                                    break
                            except:
                                pass
                except Exception as e:
                    pass

                # Línea 8: Ángulos C (azimuth)
                if len(lineas) > 7:
                    try:
                        c_values = [float(x) for x in lineas[7].split()]
                        info['angulos_c'] = c_values
                    except ValueError:
                        pass

                # Línea 9: Ángulos G (inclinación)
                if len(lineas) > 8:
                    try:
                        g_values = [float(x) for x in lineas[8].split()]
                        info['angulos_g'] = g_values
                    except ValueError:
                        pass

            # Buscar máxima intensidad en datos
            for i in range(9, min(len(lineas), 200)):
                try:
                    valores = lineas[i].split()
                    for val in valores:
                        try:
                            intensidad = float(val)
                            if intensidad > info['intensidad_max']:
                                info['intensidad_max'] = intensidad
                        except ValueError:
                            continue
                except:
                    continue

            # Si no encontramos nombre, usar archivo
            if not info['nombre']:
                info['nombre'] = os.path.splitext(
                    os.path.basename(nombre_archivo)
                )[0]

            # Si flujo es 0, estimar desde intensidad máxima
            if info['flujo_nominal'] == 0 and info['intensidad_max'] > 0:
                # Estimación aproximada: flujo ~ intensidad * ángulo sólido
                info['flujo_nominal'] = int(info['intensidad_max'] * 10)

            return info

        except Exception as e:
            print(f"⚠️ Error parseando LDT: {str(e)}")
            return None

    def obtener_lista_luminarias(self):
        """Retorna lista formateada de luminarias para dropdown"""
        lista = []
        for nombre_archivo, info in self.luminarias.items():
            # nombre_archivo es la clave que tiene la ruta completa (ej: Salvi/CLAP_M_C42_...)
            # Extraer solo el nombre sin la carpeta
            nombre_solo = nombre_archivo.split('/')[-1] if '/' in nombre_archivo else nombre_archivo

            label = nombre_solo

            if info.get('flujo_nominal'):
                label += f" - {int(info['flujo_nominal'])} lm"

            lista.append({
                'id': nombre_archivo,
                'label': label,
                'flujo': info.get('flujo_nominal', 0),
                'nombre': info.get('nombre', ''),
                'fabricante': info.get('fabricante', ''),
                'info': info
            })

        # Ordenar por nombre del archivo
        lista.sort(key=lambda x: x['label'])
        return lista

    def obtener_info_luminaria(self, id_luminaria):
        """Retorna información detallada de una luminaria"""
        return self.luminarias.get(id