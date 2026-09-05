# Guía Rápida - Cálculo Fotométrico

## 1️⃣ Primeros Pasos (5 minutos)

### Instalación

```bash
# Abrir PowerShell o CMD en la carpeta del proyecto

# Windows
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Ejecutar

```bash
python app.py
```

Abrirá: **http://localhost:5000**

## 2️⃣ Modo Manual (Entrada de Datos)

**Escenario:** Tienes UN estudio fotométrico que quieres documentar

### Pasos:

1. **Sección 1 - Proyecto**
   - Nombre: "Calle Principal - Fase 1"
   - Cliente: "Ayuntamiento de Madrid"
   - Localización: "Madrid, Centro"
   - Proyectista: "Tu nombre"
   - Fecha: 16/05/2026
   - Referencia: "MADRID-2026-001"
   - Norma: "CIE 140"

2. **Selector de Modo**
   - Seleccionar ✓ "Modo Manual"
   - Los Capítulos 2, 3, 4 se mostrarán

3. **Sección 2 - Geometría**
   - Identificador: "VIA-01"
   - Disposición: "Bilateral"
   - Altura montaje: 8 metros
   - Interdistancia: 30 metros
   - Saliente brazo: 1.5 metros
   - Inclinación: 5 grados

   **Calzada 1:**
   - Ancho: 7.5 m
   - Carriles: 2
   - Pavimento: "Asfalto"
   - Q0: 0.07
   - Clase: "ME3a"

4. **Sección 3 - Luminarias**
   - Hacer clic en "+ Añadir Luminaria"
   - Modelo: "PHILIPS SGP230"
   - Óptica LDT: "PHILIPS_SGP230_60W.ldt"
   - Potencia: 60 W
   - Objetivo: "Calzada"
   
   (Opcionalmente añadir más luminarias para aceras, etc.)

5. **Sección 4 - Energía**
   - Horas/año: 4000
   - Tarifa: 0.15 €/kWh
   - CO2: 0.285 kg/kWh
   - Zona ambiental: "E3"
   - ULOR máximo: 2.5%

6. **Sección 5 - Entregables**
   - ✓ Excel
   - ✓ Idioma: Español

7. **Enviar**
   - Clic en "Enviar Formulario"
   - Esperar respuesta
   - Descargar Excel generado

## 3️⃣ Modo Excel (Importación Masiva)

**Escenario:** Tienes MÚLTIPLES estudios en un Excel y quieres procesarlos

### Pasos:

1. **Descargar Plantilla**
   - En Sección 1, clic en "Descargar Plantilla"
   - Se descarga: `plantilla_app_salvilux.xlsx`

2. **Completar Plantilla**
   - Abrir en Excel
   - Una fila = UN estudio
   - Columnas requeridas:
     - Identificador modelo
     - Disposición
     - Altura montaje
     - Interdistancia
     - Ancho calzada 1
     - Clase calzada
     - Modelo luminaria
     - Óptica LDT
     - Potencia
     - Q0
     - Pavimento

   **Ejemplo:**
   ```
   VIA-01   | Bilateral | 8   | 30 | 7.5 | ME3a | PHILIPS SGP230 | PHILIPS_SGP230_60.ldt | 60 | 0.07 | Asfalto
   VIA-02   | Unilateral| 9   | 35 | 8.0 | ME2  | SIEMENS AS-20  | SIEMENS_AS20_70.ldt   | 70 | 0.08 | Hormigón
   ```

3. **En la Aplicación**
   - Selector de Modo: "Modo Excel"
   - Los Capítulos 2, 3, 4 desaparecen
   - Aparece: "Seleccionar archivo"

4. **Importar**
   - Clic en "Seleccionar archivo"
   - Elegir el Excel completado
   - Clic en "Importar"
   - Esperar procesamiento

5. **Descargar Resultados**
   - Se genera: `resultados_YYYYMMDD_HHMMSS.xlsx`
   - Contiene los resultados de todos los estudios

## 4️⃣ Descargar Librería LDT

**Para:** Obtener los archivos LDT de las luminarias

1. En Sección 1, clic en "📥 Descargar Librería LDT"
2. Se descarga: `LDTs_luminarias.zip`
3. Contiene estructura de carpetas por fabricante
4. Añade tus archivos LDT específicos aquí

## 5️⃣ Validaciones Automáticas

La aplicación valida automáticamente:

✅ **Campos obligatorios** (Sección 1)
✅ **Valores numéricos válidos** (Sección 2)
✅ **Rango de valores** (ej: altura 0-50m)
✅ **Mínimo 1 luminaria** (Sección 3)
✅ **Coherencia de datos** (Excel)

❌ Si falta algo, verás mensaje de error en rojo

## 6️⃣ Mensajes de Éxito

Cuando todo es correcto verás:

🟢 **"Estudio guardado correctamente"**
🟢 **"Excel procesado: X estudios encontrados"**
🟢 **"Descargando..."**

## 7️⃣ Problemas Comunes

### P: No puedo enviar el formulario
- ✓ ¿Todos los campos rojos están completos?
- ✓ ¿La altura está entre 0-50m?
- ✓ ¿Hay al menos 1 luminaria?

### P: El Excel no se importa
- ✓ ¿Es formato .xlsx?
- ✓ ¿Tiene la hoja "Plantilla"?
- ✓ ¿Tiene las columnas correctas?
- ✓ ¿El archivo no supera 50MB?

### P: No veo los Capítulos 2, 3, 4
- ✓ Cambiaste a "Modo Excel"
- ✓ En modo Excel se ocultan estos capítulos (por diseño)
- ✓ Vuelve a "Modo Manual" para verlos

### P: La app no inicia
```bash
# Verifica Python instalado
python --version

# Verifica dependencias
pip install -r requirements.txt

# Verifica que no hay error
python app.py
```

## 8️⃣ Atajos del Teclado

- **Tab**: Navegar entre campos
- **Enter**: Enviar formulario
- **Esc**: Cerrar mensajes de error

## 9️⃣ Documentación Completa

Ver: `README.md` para documentación detallada

## 🔟 Soporte

❓ Problemas o preguntas: elizalde@salvi.es

---

**¡Listo!** Ya estás preparado para usar la aplicación. 🚀
