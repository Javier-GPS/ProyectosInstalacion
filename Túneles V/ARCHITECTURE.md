# Arquitectura Técnica - Cálculo Fotométrico

## Descripción General

Aplicación web de cálculo fotométrico construida con arquitectura cliente-servidor.

```
┌─────────────────────┐
│   Navegador Web     │  (Cliente)
│   - HTML/CSS/JS     │
└──────────┬──────────┘
           │ HTTP/JSON
           ↓
┌─────────────────────┐
│   Flask Server      │  (Servidor)
│   - app.py          │
│   - routes/         │
└──────────┬──────────┘
           │
      ┌────┴────┬────────┬──────────┐
      ↓         ↓        ↓          ↓
   Módulos  Validación  Excel    Archivos
  usuarios  de datos   Handler   locales
```

## Stack Tecnológico

### Backend
- **Framework:** Flask 2.3.3 (Python web framework)
- **Librerías:**
  - `openpyxl 3.1.2` - Lectura/escritura de archivos Excel
  - `pandas 2.0.3` - Procesamiento de datos tabulares
  - `Werkzeug 2.3.7` - WSGI utilities
  - `python-dotenv 1.0.0` - Gestión de variables de entorno

### Frontend
- **HTML5** - Estructura semántica
- **CSS3** - Diseño responsivo con grid y flexbox
- **Vanilla JavaScript** - Lógica del lado del cliente (sin frameworks)
- **Fetch API** - Comunicación asíncrona con servidor

### Servidor
- **Python 3.8+** - Interpretador
- **pip** - Gestor de paquetes
- **Gunicorn/Waitress** - Servidor WSGI (producción)

## Estructura de Carpetas

```
project_root/
│
├── app.py
│   └── Entrada principal de la aplicación Flask
│       - Define rutas y endpoints
│       - Maneja solicitudes HTTP
│       - Gestión de errores
│
├── config.py
│   └── Configuración centralizada
│       - Rutas de archivos
│       - Límites de tamaño
│       - Validaciones
│       - Opciones de desplegables
│
├── requirements.txt
│   └── Dependencias Python
│
├── modules/
│   │
│   ├── __init__.py
│   │   └── Marca como paquete Python
│   │
│   ├── validators.py
│   │   └── Clase DataValidator
│   │       - validate_form_data()
│   │       - validate_excel_data()
│   │       - sanitize_data()
│   │
│   └── excel_handler.py
│       └── Clase ExcelHandler
│           - create_study_from_form()
│           - process_imported_excel()
│           - create_results_excel()
│           - _style_cell()
│           - _write_header()
│
├── templates/
│   └── index.html
│       └── Interfaz web completa
│           - Sección 1: Proyecto/Cliente
│           - Sección 2: Geometría
│           - Sección 3: Luminarias
│           - Sección 4: Energía/Ambiental
│           - Sección 5: Entregables
│           - CSS integrado (grid 3 columnas)
│           - JavaScript para interactividad
│
├── assets/
│   ├── plantilla_app_salvilux.xlsx
│   │   └── Plantilla para importación masiva
│   │       11 columnas predefinidas
│   │       5 filas de ejemplo
│   │
│   └── LDTs_luminarias.zip
│       └── Librería de archivos LDT
│           Estructura por fabricante
│
├── uploads/
│   └── Archivos importados (temporal)
│       Auto-eliminados después del procesamiento
│
└── downloads/
    └── Archivos generados
        Disponibles para descargar por usuario
```

## Flujo de Datos

### Modo Manual (Entrada de Datos)

```
Formulario Web
    ↓
JavaScript recolecta datos
    ↓
POST /api/submit-form (JSON)
    ↓
Flask recibe solicitud
    ↓
DataValidator.validate_form_data()
    ├─ Verifica campos obligatorios
    ├─ Valida rangos numéricos
    └─ Valida luminarias
    ↓
ExcelHandler.create_study_from_form()
    ├─ Crea Workbook nuevo
    ├─ Hoja "Proyecto" (datos básicos)
    ├─ Hoja "Geometría" (vía, calzadas, aceras)
    ├─ Hoja "Luminarias" (tabla de luminarias)
    └─ Hoja "Energía" (parámetros)
    ↓
Archivo Excel guardado en /downloads
    ↓
Retorna URL de descarga
    ↓
Cliente descarga archivo
```

### Modo Excel (Importación Masiva)

```
Plantilla Excel completada
    ↓
Usuario selecciona archivo
    ↓
POST /api/upload-excel (multipart)
    ↓
Flask recibe y guarda en /uploads
    ↓
ExcelHandler.process_imported_excel()
    ├─ Lee encabezados
    ├─ Mapea columnas a campos
    ├─ Itera filas
    ├─ Convierte tipos de datos
    └─ Retorna lista de estudios
    ↓
DataValidator.validate_excel_data()
    ├─ Valida columnas presentes
    ├─ Valida datos no nulos
    └─ Valida tipos numéricos
    ↓
ExcelHandler.create_results_excel()
    ├─ Crea Workbook "Resultados"
    ├─ Encabezados
    └─ Una fila por estudio procesado
    ↓
Archivo temporal eliminado de /uploads
    ↓
Archivo de resultados en /downloads
    ↓
Retorna URL de descarga
    ↓
Cliente descarga archivo
```

## Endpoints API

### GET `/`
**Descripción:** Página principal
**Retorna:** HTML del formulario
**Status:** 200

### POST `/api/submit-form`
**Descripción:** Genera Excel desde formulario manual
**Content-Type:** application/json
**Body:** Datos del formulario (20+ campos)

**Validaciones:**
1. Campos obligatorios presentes
2. Valores numéricos válidos
3. Rangos correctos
4. Mínimo 1 luminaria

**Respuesta Exitosa:**
```json
{
  "success": true,
  "message": "Excel generado correctamente",
  "download_url": "/api/download/estudio_20260516_143022.xlsx"
}
```

**Respuesta Error (400):**
```json
{
  "success": false,
  "errors": [
    "Nombre del proyecto es obligatorio",
    "Altura de montaje debe estar entre 0 y 50"
  ]
}
```

### POST `/api/upload-excel`
**Descripción:** Procesa archivo Excel con múltiples estudios
**Content-Type:** multipart/form-data
**Field:** file (Excel)

**Validaciones:**
1. Archivo presente
2. Extensión .xlsx o .xls
3. Tamaño < 50MB
4. Hoja "Plantilla" existe
5. Columnas requeridas presentes

**Respuesta Exitosa:**
```json
{
  "success": true,
  "message": "Excel procesado: 5 estudios encontrados",
  "download_url": "/api/download/resultados_20260516_143022.xlsx"
}
```

**Respuesta Error (400):**
```json
{
  "success": false,
  "error": "Hoja 'Plantilla' no encontrada"
}
```

### GET `/api/download-template`
**Descripción:** Descarga plantilla Excel vacía
**Retorna:** Archivo Excel
**Content-Type:** application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
**Status:** 200

### GET `/api/download-ldts`
**Descripción:** Descarga librería LDT
**Retorna:** Archivo ZIP
**Content-Type:** application/zip
**Status:** 200

### GET `/api/download/<filename>`
**Descripción:** Descarga archivo generado
**Parámetros:** filename (sanitizado)
**Retorna:** Archivo solicitado
**Status:** 200 o 404

**Seguridad:** Usa `secure_filename()` para prevenir path traversal

### GET `/api/health`
**Descripción:** Health check del servidor
**Retorna:** 
```json
{
  "status": "ok",
  "timestamp": "2026-05-16T15:30:45.123456"
}
```

## Validaciones

### En el Cliente (JavaScript)
- Campos vacíos (validación HTML5 `required`)
- Tipos de datos (HTML5 `type=number`)
- Rangos (HTML5 `min`/`max`)
- Visualización previa de archivos

### En el Servidor (Python)

**DataValidator.validate_form_data():**
- Campos obligatorios: 6 (Sección 1)
- Si modo='manual':
  - Campos de geometría: 6
  - Rangos numéricos: 3 (altura, interdistancia, saliente)
  - Luminarias: Mínimo 1 con todos los campos

**DataValidator.validate_excel_data():**
- DataFrame no vacío
- 11 columnas requeridas presentes
- Filas sin identificador o luminaria descartadas
- Valores numéricos convertibles a float

**ExcelHandler.process_imported_excel():**
- Itera filas saltando errors de conversión
- Guarda solo filas válidas
- Retorna lista de diccionarios

## Gestión de Archivos

### Directorio `/uploads`
- Archivos importados por usuarios
- Temporal: eliminados después de procesar
- Máximo 50MB por archivo

### Directorio `/downloads`
- Archivos Excel generados
- Disponibles para descargar
- Nombrados con timestamp: `estudio_YYYYMMDD_HHMMSS.xlsx`
- No auto-limpios (considerar limpiar antiguos periódicamente)

### Directorio `/assets`
- Archivos estáticos del sistema
- Plantilla Excel base
- Librería LDT (ZIP)

## Seguridad

### Protecciones Implementadas

1. **Sanitización de filenames**
   ```python
   secure_filename(file.filename)
   ```
   Previene path traversal attacks

2. **Límite de tamaño de archivo**
   ```python
   MAX_CONTENT_LENGTH = 50MB
   ```
   Previene exhaustión de recursos

3. **Extensiones permitidas**
   ```python
   ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
   ```
   Solo archivos Excel

4. **Validación de entrada**
   - Campos requeridos
   - Tipos de datos
   - Rangos de valores

5. **Manejo de errores**
   - Excepción genérica (no expone detalles internos)
   - Mensajes de error específicos solo en desarrollo

### Consideraciones de Producción

- [ ] HTTPS/SSL obligatorio
- [ ] Rate limiting en endpoints
- [ ] Autenticación de usuarios
- [ ] Autorización (ver solo propios estudios)
- [ ] CORS configurado correctamente
- [ ] CSRF protection en formularios
- [ ] Logging y monitoreo
- [ ] Backup automático de archivos

## Performance

### Optimizaciones Actuales

1. **Frontend**
   - Vanilla JS (sin frameworks pesados)
   - CSS grid (layout eficiente)
   - Carga inline (una sola solicitud HTML)

2. **Backend**
   - openpyxl (eficiente para Excel)
   - Lectura secuencial de filas (bajo uso de memoria)
   - Eliminación inmediata de temporales

### Mejoras Futuras

1. Caché de plantillas
2. Procesamiento asíncrono (Celery)
3. Compresión de respuestas
4. CDN para archivos estáticos
5. Base de datos para historial de estudios

## Escalabilidad

### Configuración Actual
- Single-threaded development server
- Adecuado para <10 usuarios concurrentes

### Para Producción

1. **Servidor WSGI**
   ```bash
   gunicorn --workers 4 --threads 2 app:app
   ```

2. **Load Balancer**
   - nginx o HAProxy
   - Distribuye solicitudes

3. **Base de Datos**
   - PostgreSQL o MySQL
   - Persistencia de estudios

4. **Cache**
   - Redis para sesiones
   - Cache de plantillas

5. **Almacenamiento**
   - S3 o similar para archivos grandes
   - Limpieza automática de temporales

## Monitoreo y Logging

### Logs Importantes

```python
# En app.py
app.logger.info(f"Excel generado: {filename}")
app.logger.error(f"Error al procesar Excel: {str(e)}")
```

### Métricas

- Número de solicitudes por tipo
- Tiempo de procesamiento por operación
- Errores y excepciones
- Tamaño de archivos generados

## Versionado

- **API Version:** 1.0
- **Aplicación Version:** 1.0
- **Python:** 3.8+
- **Flask:** 2.3.3

## Roadmap

1. **v1.1**
   - Cálculo automático de iluminancia
   - Generación de PDF

2. **v2.0**
   - Autenticación de usuarios
   - Base de datos de estudios
   - API GraphQL
   - App móvil

3. **v3.0**
   - Visor 3D de geometría
   - Simulación de luz en tiempo real
   - Integración con Salvi

---

Documento actualizado: 2026-05-16
