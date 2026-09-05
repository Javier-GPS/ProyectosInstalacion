# Solución de Problemas - SalviLux

## Problema: El script run.bat falla al instalar dependencias

### Síntomas:
- Ves caracteres raros/codificación incorrecta
- Sale error al instalar dependencias
- No se abre la aplicación en el navegador

### Soluciones:

#### Opción 1: Usar el script simplificado (RECOMENDADO)
```
1. Haz doble clic en: run_simple.bat
2. Espera a que se instalen las dependencias
3. Se abrirá automáticamente en http://localhost:5000
```

#### Opción 2: Instalación manual paso a paso
```
1. Abre CMD (línea de comandos)
2. Navega a la carpeta del proyecto:
   cd "C:\Users\[TU_USUARIO]\OneDrive - C.M. SALVI\Documentos\Claude\Projects\CALCULO FOTOMETRICO SALVI"

3. Crea el entorno virtual:
   python -m venv venv

4. Actívalo:
   venv\Scripts\activate.bat

5. Instala las dependencias:
   pip install Flask==2.3.3 openpyxl==3.1.2 pandas==2.0.3 Werkzeug==2.3.7 python-dotenv==1.0.0

6. Ejecuta la aplicación:
   python app.py

7. Abre en tu navegador:
   http://localhost:5000
```

#### Opción 3: Instalar dependencias una a una (si hay problema)
```
venv\Scripts\activate.bat
pip install Flask==2.3.3
pip install openpyxl==3.1.2
pip install pandas==2.0.3
pip install Werkzeug==2.3.7
pip install python-dotenv==1.0.0
python app.py
```

## Problema: "Port 5000 already in use"

El puerto 5000 está en uso por otra aplicación.

### Solución:
Edita `app.py` y en la última línea (alrededor de línea 166), cambia:
```python
app.run(debug=True, host='0.0.0.0', port=5000)
```

Por:
```python
app.run(debug=True, host='0.0.0.0', port=5001)
```

Luego abre: `http://localhost:5001`

## Problema: "Python no reconocido"

Python no está en PATH o no está instalado.

### Solución:
1. **Descarga Python** desde: https://www.python.org/downloads/
2. **Instala con estas opciones:**
   - ✓ Marca: "Add Python to PATH"
   - ✓ Marca: "Install pip"
3. **Reinicia tu PC**
4. Abre CMD de nuevo y prueba: `python --version`

## Problema: No se abre la aplicación automáticamente

### Solución:
1. Verifica en la terminal que dice: "Running on http://localhost:5000"
2. Abre tu navegador manualmente (Chrome, Firefox, Edge, Safari)
3. Escribe en la barra de dirección: `http://localhost:5000`
4. Presiona Enter

## Problema: Veo errores de importación

Ejemplo: `ModuleNotFoundError: No module named 'flask'`

### Solución:
```
1. Asegúrate de que el entorno virtual está ACTIVADO
2. En la terminal debe decir (venv) al inicio de la línea
3. Si no está activado, ejecuta:
   venv\Scripts\activate.bat
4. Luego reinstala:
   pip install -r requirements.txt
```

## Problema: El formulario no se ve o está extraño

### Solución:
1. Presiona **Ctrl + Shift + R** para recargar con caché vacío
2. O abre en modo incógnito/privado
3. Prueba en otro navegador (Chrome, Firefox, Edge)

## Archivos importantes del proyecto:

```
CALCULO FOTOMETRICO SALVI/
├── run.bat                 ← Script principal
├── run_simple.bat         ← Script simplificado (RECOMENDADO)
├── app.py                 ← Aplicación Flask
├── requirements.txt       ← Dependencias
├── config.py              ← Configuración
├── modules/               ← Módulos Python
├── templates/index.html   ← Interfaz web
└── assets/                ← Plantillas y librerías
```

## ¿Necesitas más ayuda?

📧 **Email:** elizalde@salvi.es

Incluye:
- Captura de pantalla del error
- Versión de Python: `python --version`
- Sistema operativo (Windows, Mac, Linux)
- Pasos exactos que seguiste
