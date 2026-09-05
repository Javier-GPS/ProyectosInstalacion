# Guía de Instalación - Cálculo Fotométrico

## Prerrequisitos

- **Python 3.8 o superior**
- **pip** (gestor de paquetes Python)
- **Navegador web moderno** (Chrome, Firefox, Safari, Edge)

## Verificar Instalación de Python

Abre PowerShell, CMD o Terminal y ejecuta:

```bash
python --version
```

O en algunos sistemas:

```bash
python3 --version
```

Deberías ver algo como: `Python 3.10.5`

Si no está instalado, descárgalo desde: https://www.python.org/downloads/

## Pasos de Instalación

### 1. Descargar el Proyecto

```bash
cd "C:\Users\[TU_USUARIO]\OneDrive - C.M. SALVI\Documentos\Claude\Projects"
```

O la ruta donde tengas el proyecto.

### 2. Acceder a la Carpeta del Proyecto

```bash
cd "CALCULO FOTOMETRICO SALVI"
```

### 3. Crear Entorno Virtual (Recomendado)

**En Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**En macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

Deberías ver `(venv)` al inicio de tu línea de comando.

### 4. Instalar Dependencias

```bash
pip install -r requirements.txt
```

Espera a que finalice. Verás mensajes como:
```
Successfully installed Flask-2.3.3 openpyxl-3.1.2 ...
```

### 5. Verificar Instalación (Opcional pero Recomendado)

```bash
python test_setup.py
```

Deberías ver todos los checkmarks (✓) en verde. Si algo está en rojo (✗), revisa los pasos anteriores.

## Ejecución

### Iniciar la Aplicación

```bash
python app.py
```

Deberías ver:
```
 * Serving Flask app 'app'
 * Debug mode: on
 * Running on http://0.0.0.0:5000
```

### Acceder a la Aplicación

Abre tu navegador y ve a:

```
http://localhost:5000
```

Deberías ver el formulario de cálculo fotométrico.

## Estructura del Proyecto

```
CALCULO FOTOMETRICO SALVI/
│
├── 📄 app.py                          # Aplicación Flask principal
├── 📄 config.py                       # Configuración
├── 📄 requirements.txt                # Dependencias Python
├── 📄 test_setup.py                   # Script de verificación
│
├── 📁 modules/
│   ├── __init__.py
│   ├── validators.py                  # Validación de datos
│   └── excel_handler.py               # Manejo de Excel
│
├── 📁 templates/
│   └── index.html                     # Interfaz web
│
├── 📁 assets/
│   ├── plantilla_app_salvilux.xlsx      # Plantilla para importación
│   └── LDTs_luminarias.zip            # Librería de LDTs
│
├── 📁 uploads/                        # Archivos importados (se crea automáticamente)
├── 📁 downloads/                      # Archivos generados (se crea automáticamente)
│
└── 📄 README.md                       # Documentación completa
```

## Solución de Problemas

### Error: "Python no reconocido"

**Problema:** El comando `python` no funciona
**Solución:**
- Windows: Reinstala Python y marca "Add Python to PATH" durante la instalación
- macOS/Linux: Usa `python3` en lugar de `python`

### Error: "No module named 'flask'"

**Problema:** Las dependencias no están instaladas
**Solución:**
```bash
pip install -r requirements.txt
```

### Error: "Port 5000 already in use"

**Problema:** Otro programa usa el puerto 5000
**Solución:**

**Windows:**
```bash
netstat -ano | findstr :5000
taskkill /PID [PID] /F
```

**macOS/Linux:**
```bash
lsof -i :5000
kill -9 [PID]
```

O cambia el puerto en `app.py` línea 166:
```python
app.run(debug=True, host='0.0.0.0', port=5001)  # Cambia a 5001
```

Luego accede a: `http://localhost:5001`

### Error: "Template 'index.html' not found"

**Problema:** La carpeta `templates/` no está en el lugar correcto
**Solución:**
- Verifica que `templates/index.html` existe
- Asegúrate de ejecutar `python app.py` desde la carpeta raíz del proyecto

### Error: "assets/plantilla_app_salvilux.xlsx not found"

**Problema:** Los archivos en `assets/` no existen
**Solución:**
- Verifica que la carpeta `assets/` contiene los dos archivos:
  - `plantilla_app_salvilux.xlsx`
  - `LDTs_luminarias.zip`

### Error: "File too large"

**Problema:** El archivo Excel excede 50MB
**Solución:**
- Reduce el tamaño del Excel
- O cambia el límite en `config.py`:
  ```python
  MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
  ```

## Modo Desarrollo vs Producción

### Desarrollo (por defecto)

```bash
python app.py
```

- Debug activado
- Recargas automáticas
- Mensajes de error detallados

### Producción (recomendado para servidor)

Instala `gunicorn`:
```bash
pip install gunicorn
```

Ejecuta con:
```bash
gunicorn --bind 0.0.0.0:5000 app:app
```

O en Windows:
```bash
pip install waitress
waitress-serve --port=5000 app:app
```

## Despliegue en Servidor

Para desplegar en un servidor remoto:

1. **Instala Python en el servidor**
2. **Copia el proyecto completo**
3. **Crea entorno virtual e instala dependencias**
4. **Configura un gestor de procesos:**

   **Linux (systemd):**
   
   Crea `/etc/systemd/system/fotometrico.service`:
   ```
   [Unit]
   Description=Cálculo Fotométrico
   After=network.target

   [Service]
   User=www-data
   WorkingDirectory=/home/app/fotometrico
   ExecStart=/home/app/fotometrico/venv/bin/gunicorn --bind 0.0.0.0:5000 app:app
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

   Luego:
   ```bash
   sudo systemctl start fotometrico
   sudo systemctl enable fotometrico
   ```

5. **Configura un proxy reverso (nginx):**

   ```nginx
   server {
       listen 80;
       server_name fotometrico.example.com;

       location / {
           proxy_pass http://127.0.0.1:5000;
       }
   }
   ```

## Variables de Entorno

Crea un archivo `.env` (opcional) para configuración personalizada:

```bash
cp .env.example .env
```

Edita `.env` con tus valores:

```
FLASK_ENV=production
SECRET_KEY=tu-clave-secreta-fuerte
SERVER_PORT=5000
MAX_FILE_SIZE_MB=50
```

## Mantenimiento

### Limpiar Archivos Antiguos

```bash
# Eliminar uploads temporales
rm -rf uploads/*

# Eliminar downloads antiguos (mantener últimos 7 días)
find downloads -mtime +7 -delete
```

### Actualizar Dependencias

```bash
pip install --upgrade -r requirements.txt
```

### Hacer Backup del Proyecto

```bash
tar -czf fotometrico_backup_$(date +%Y%m%d).tar.gz .
```

## Contacto y Soporte

Para problemas, preguntas o sugerencias:

📧 **Email:** elizalde@salvi.es

---

**Felicidades!** Ya tienes la aplicación instalada y lista para usar. 🚀

Próximo paso: Leer `QUICKSTART.md` para empezar a usar la aplicación.
