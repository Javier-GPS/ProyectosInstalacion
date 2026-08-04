# SalviLux - Cálculo Fotométrico

## 🚀 INICIO RÁPIDO (3 clics)

### Windows - Opción 1: Script Batch (MÁS FÁCIL)

1. **Abre la carpeta del proyecto** en tu explorador
2. **Haz doble clic en:** `EJECUTAR.bat`
3. **Espera** a que termine (verás: "OK" en cada paso)
4. **Automáticamente** se abrirá: `http://localhost:5000`

### Windows - Opción 2: PowerShell (MÁS BONITO)

1. **Click derecho** en la carpeta del proyecto → "Open PowerShell window here"
2. **Ejecuta:** `.\EJECUTAR.ps1`
3. **Espera** a que termine
4. **Abre navegador:** `http://localhost:5000`

Si tienes error de permisos, ejecuta primero:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## 🔧 INSTALACIÓN MANUAL (Si los scripts fallan)

### Paso 1: Abre CMD o PowerShell

- **Windows 10/11:** Presiona `Win + X` → "Windows Terminal" o "Command Prompt"
- Navega a la carpeta del proyecto

### Paso 2: Crea el entorno virtual

```bash
python -m venv venv
```

### Paso 3: Actívalo

**En CMD:**
```bash
venv\Scripts\activate.bat
```

**En PowerShell:**
```powershell
.\venv\Scripts\Activate.ps1
```

### Paso 4: Instala las dependencias

```bash
pip install Flask==2.3.3 openpyxl==3.1.2 pandas==2.0.3 Werkzeug==2.3.7 python-dotenv==1.0.0
```

### Paso 5: Ejecuta la aplicación

```bash
python app.py
```

### Paso 6: Abre en navegador

```
http://localhost:5000
```

---

## ❓ PROBLEMAS Y SOLUCIONES

### "Python no encontrado"

**Solución:**
1. Descarga Python: https://www.python.org/downloads/
2. **IMPORTANTE:** Durante la instalación, marca "Add Python to PATH"
3. Reinicia tu computadora
4. Vuelve a intentar

### "Port 5000 already in use"

El puerto está ocupado por otra aplicación.

**Soluciones:**
- Cierra otras aplicaciones que usen el puerto 5000
- O edita `app.py` última línea y cambia `port=5000` a `port=5001`

### "ModuleNotFoundError: No module named 'flask'"

**Solución:**
1. Verifica que el entorno virtual está ACTIVADO (debe decir `(venv)` al inicio de la línea)
2. Reinstala: `pip install -r requirements.txt`

### "Permission denied" en PowerShell

**Solución:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## 📱 USANDO LA APLICACIÓN

Una vez que veas en la terminal:
```
Running on http://localhost:5000
```

### Modo Manual:
1. Completa la Sección 1 (Proyecto/Cliente)
2. Selecciona **Modo Manual**
3. Rellena Secciones 2-5
4. Presiona **GENERAR EXCEL** (botón negro grande)
5. Descarga el archivo generado

### Modo Excel:
1. En la app: Presiona **Descargar Plantilla**
2. Abre el Excel descargado
3. Completa los datos (una fila = un estudio)
4. En la app: Selecciona **Modo Excel**
5. Importa el archivo
6. Presiona **PROCESAR EXCEL**
7. Descarga los resultados

---

## 🛑 PARA DETENER LA APLICACIÓN

Presiona **Ctrl + C** en la terminal

---

## 📊 ARCHIVOS IMPORTANTES

```
CALCULO FOTOMETRICO SALVI/
├── EJECUTAR.bat              ← HAZA DOBLE CLIC AQUÍ
├── EJECUTAR.ps1              ← Alternativa PowerShell
├── app.py                    ← Aplicación Flask
├── requirements.txt          ← Dependencias
├── config.py                 ← Configuración
├── templates/
│   └── index.html            ← Interfaz web
├── modules/
│   ├── validators.py         ← Validaciones
│   └── excel_handler.py       ← Manejo de Excel
└── assets/
    ├── plantilla_app_salvilux.xlsx
    └── LDTs_luminarias.zip
```

---

## 🎓 DOCUMENTACIÓN ADICIONAL

- **QUICKSTART.md** - Guía rápida de uso
- **SOLUCIONAR_PROBLEMAS.md** - Más soluciones
- **README.md** - Manual completo
- **ARCHITECTURE.md** - Detalles técnicos

---

## 📞 SOPORTE

Si tienes problemas:
1. Lee **SOLUCIONAR_PROBLEMAS.md**
2. Verifica que Python está en PATH: `python --version`
3. Contacta: elizalde@salvi.es

---

**¡Listo para usar!** 🎉
