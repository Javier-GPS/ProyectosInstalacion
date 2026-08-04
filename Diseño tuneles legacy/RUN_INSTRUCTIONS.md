# 🚀 Cómo Ejecutar la Aplicación

## Opción 1: Script Batch (.bat) - RECOMENDADO PARA PRINCIPIANTES

### En Windows (Cualquier versión)

1. **Abre el Explorador de Archivos** y navega a la carpeta del proyecto:
   ```
   C:\Users\[TU_USUARIO]\OneDrive - C.M. SALVI\Documentos\Claude\Projects\CALCULO FOTOMETRICO SALVI
   ```

2. **Haz doble clic en el archivo `run.bat`**

3. **Se abrirá una ventana de terminal que hará:**
   - ✅ Verificar que Python está instalado
   - ✅ Crear el entorno virtual (si no existe)
   - ✅ Instalar dependencias (si no están)
   - ✅ Verificar archivos del proyecto
   - ✅ Iniciar el servidor Flask

4. **Abre tu navegador** y ve a:
   ```
   http://localhost:5000
   ```

### Ventajas del .bat
- ✅ Solo haz doble clic para ejecutar
- ✅ Funciona en cualquier versión de Windows
- ✅ Verifica todo automáticamente
- ✅ Fácil de entender

---

## Opción 2: Script PowerShell (.ps1) - MÁS MODERNO

### En Windows 10+ (Con PowerShell)

1. **Abre PowerShell** (no CMD, debe ser PowerShell)
   - Click derecho en la carpeta del proyecto
   - Selecciona "Open PowerShell window here"
   - O presiona `Shift + Click derecho` en la carpeta

2. **Ejecuta el script:**
   ```powershell
   .\run.ps1
   ```

3. **Si ves un error de permisos:**
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   .\run.ps1
   ```

4. **Abre tu navegador** y ve a:
   ```
   http://localhost:5000
   ```

### Ventajas del .ps1
- ✅ Colores y mensajes más claros
- ✅ Mejor manejo de errores
- ✅ Más moderno que batch
- ✅ Más fácil de leer

---

## Opción 3: Manual (Línea de Comandos)

### Si prefieres hacerlo paso a paso:

1. **Abre CMD o PowerShell** en la carpeta del proyecto

2. **Instala dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Ejecuta la aplicación:**
   ```bash
   python app.py
   ```

4. **Abre en navegador:**
   ```
   http://localhost:5000
   ```

---

## 🔧 Solución de Problemas

### Error: "Python no reconocido"

**Solución:**
1. Instala Python desde: https://www.python.org/downloads/
2. **IMPORTANTE**: Marca la casilla "Add Python to PATH" durante la instalación
3. Reinicia tu PC
4. Ejecuta nuevamente

### Error: "No se puede ejecutar run.bat"

**Solución:**
- Haz clic derecho en `run.bat`
- Selecciona "Run as administrator"
- O abre CMD y escribe:
  ```cmd
  cd "C:\ruta\a\carpeta"
  run.bat
  ```

### Error: "Port 5000 already in use"

**Solución:**
- El puerto 5000 está siendo usado por otra aplicación
- Opción 1: Cierra la otra aplicación
- Opción 2: Edita `app.py` línea 166 y cambia el puerto:
  ```python
  app.run(debug=True, host='0.0.0.0', port=5001)
  ```

### Error: "Permission denied" en PowerShell

**Solución:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## ✅ ¿Cómo sé que está funcionando?

Verás algo como esto en la ventana de terminal:

```
✓ Python 3.10.5 encontrado
✓ Entorno virtual encontrado
✓ Dependencias ya están instaladas
✓ app.py encontrado
✓ templates\index.html encontrado

🚀 La aplicación estará disponible en:
   http://localhost:5000

Presiona Ctrl+C para detener el servidor
```

Y en tu navegador verás el formulario de la aplicación de cálculo fotométrico.

---

## 🛑 Para detener la aplicación

Presiona **Ctrl + C** en la ventana del terminal donde está corriendo Flask

---

## 💡 Crear un Acceso Directo en el Escritorio

### Para .bat:
1. Haz clic derecho en `run.bat`
2. Selecciona "Send to" → "Desktop (create shortcut)"
3. Ya está! Ahora puedes ejecutar desde el escritorio

### Para .ps1:
1. Haz clic derecho en el escritorio
2. New → Shortcut
3. En la ubicación escribe:
   ```
   powershell.exe -ExecutionPolicy RemoteSigned -File "C:\ruta\completa\a\run.ps1"
   ```
4. Cambia el nombre a "Cálculo Fotométrico"
5. Click en Aceptar

---

## 📱 Usando la Aplicación

Una vez que el servidor esté corriendo (http://localhost:5000):

### Modo Manual:
1. Completa la Sección 1 (Proyecto/Cliente)
2. Selecciona "Modo Manual"
3. Rellena las Secciones 2, 3, 4, 5
4. Presiona "Enviar"
5. Descarga el Excel generado

### Modo Excel:
1. Haz clic en "Descargar Plantilla"
2. Completa la plantilla con múltiples estudios
3. En la app: Selecciona "Modo Excel"
4. Importa el archivo
5. Descarga los resultados

Ver **QUICKSTART.md** para más detalles.

---

## 🔄 Cómo actualizar en el futuro

Si necesitas actualizar el proyecto:

1. Simplemente copia los archivos nuevos
2. Ejecuta nuevamente `run.bat` o `run.ps1`
3. **No necesitas hacer nada más**, los scripts manejan todo automáticamente

---

## 📞 Soporte

Si algo no funciona:

1. Lee **INSTALL.md** (guía de instalación completa)
2. Verifica los "Solución de Problemas" arriba
3. Contacta: elizalde@salvi.es

---

## ✨ Atajos Útiles

| Acción | Atajo |
|--------|-------|
| Detener servidor | Ctrl + C |
| Recargar navegador | Ctrl + R |
| Forzar recargar (borrar caché) | Ctrl + Shift + R |
| Abrir DevTools | F12 |
| Cambiar puerto en app.py | Edita línea 166 |

---

**¡Listo para empezar!** 🎉
