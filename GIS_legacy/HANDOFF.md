# SALVI GIS — Documento de traspaso (handoff)

> Estado del proyecto y plan de trabajo para continuar el desarrollo (en Claude Code o donde sea).
> Última actualización: 2026-07-15.

---

## 1. Qué es el proyecto

Herramienta web de **análisis y diseño de alumbrado público urbano**. Carga datos reales
de OpenStreetMap (OSM), clasifica la red viaria, calcula necesidades de iluminación según
**EN 13201**, y exporta inventario de luminarias y plantillas para cálculo fotométrico.

Pensada para proyectos en Angola, Mauritania, Senegal, Egipto, Rwanda, Benín y España.

### Dos fases de trabajo (clave del diseño actual)

1. **Fase 1 — Planificación / estimación preliminar.** Desde una zona se buscan calles en OSM,
   se aplican valores por defecto (clase lumínica, interdistancia…) y se estiman rangos de
   proyecto para presentar a un cliente/político. Vista *maestra* sobre muchas zonas.

2. **Fase 2 — Detalle / replanteo.** Sobre una zona concreta se editan posiciones de luminarias,
   interdistancias y disposiciones, se envía a **Lux Studio** (intercambio por Excel; en el futuro,
   API directa) y se importan los resultados fotométricos para visualizar cumplimiento en el mapa.

---

## 2. Arquitectura y ficheros

| Fichero | Rol |
|---|---|
| `SALVI GIS.html` | Frontend completo (~11.000 líneas): HTML + CSS + JS en un solo archivo. Mapa MapLibre GL. |
| `api_server.py`  | Backend Python (stdlib `http.server`, sin frameworks). ~1.560 líneas. Puerto **8733**. |
| `db/salvi_gis.db`| SQLite. Zonas, proyectos, luminarias, inventario, resultados fotométricos, usuarios. |
| `db/salvi_gis - copia.db` | Copia de seguridad de datos (SIN tabla `users`). |
| `fix_db.py`      | Utilidad: repara BD dañada desde la copia y crea/resetea usuario admin. |
| `reset_password.py` | Utilidad CLI de gestión de usuarios (listar/reset/crear/borrar). |
| `Abrir SALVI GIS.bat` | Lanzador Windows: mata puertos 8732/8733, arranca backend + servidor estático (8732) y abre Chrome. |
| `.env`           | Config: `AUTH_SECRET` (JWT), `ANTHROPIC_API_KEY`, `SMTP_*` opcional. **No commitear.** |

### Cómo arrancar
```
python fix_db.py        # solo si la BD está dañada o falta el usuario
Abrir SALVI GIS.bat     # arranca todo y abre el navegador
```
Frontend servido en `http://localhost:8732/SALVI GIS.html`, backend en `http://localhost:8733`.

---

## 3. Autenticación (cómo funciona)

- JWT HS256 firmado con `AUTH_SECRET` (persistido en `.env`, estable entre reinicios).
- Token guardado en `localStorage['_salvi_token']`. Cabecera `Authorization: Bearer <token>`.
- TTL 7 días (30 días si "Recordarme"). Hash de contraseña PBKDF2-SHA256, 600k iteraciones.
- Rutas públicas: `/api/auth/login`, `/api/auth/setup`. El resto exige token.
- Recuperación de contraseña por token (in-memory, 1h) — SMTP opcional; si no, el admin copia el código.

### ⚠️ Gotcha importante
Si se **reconstruye la BD** (restaurar desde copia + recrear usuario), el **uid del usuario cambia**.
Los tokens antiguos en el navegador apuntan a un uid inexistente → **401 en todo**.
**Solución:** cerrar sesión y volver a entrar (o `localStorage.clear()` + recarga). No es un bug de datos.

---

## 4. Historial reciente de trabajo (hecho)

- ✅ Reescrita la sección de **AYUDA** completa en 5 idiomas (ES/EN/PT/FR/CA), 11 secciones.
- ✅ Panel de ayuda **no bloqueante** (se puede trabajar con la ayuda abierta; sin desenfoque).
- ✅ **Autenticación robusta**: login, "recordarme" (30 días), recuperación por token/email, gestión de usuarios (admin).
- ✅ **Recuperación de BD**: la BD live se corrompió (sync OneDrive); `fix_db.py` restaura desde copia + recrea usuario.
- ✅ Reparado `api_server.py` que quedó **truncado** por una edición (faltaban handlers + `run()`).
- ✅ **Export DXF** con modal de capas.
- ✅ Capa de **árboles OSM** (mapa + BD + DXF).
- ✅ Arreglados **401** en export plantilla luminotécnica e import fotométrico (faltaban cabeceras auth / URL hardcodeada).
- ✅ **Fase 1 del Modo Detalle** (ver §5): conmutador de modo + layout de paneles acoplados.

---

## 5. Modo Detalle — plan de desarrollo (decidido con el cliente)

Sustituir la ventana **flotante** de trabajo de detalle (poco funcional) por un **modo conmutable**
que reconfigura toda la pantalla. Decisión del cliente: **modo conmutable** (no ventana aparte).

**Distribución (Fase 1, ya implementada):**
- Conmutador en la cabecera: `🗺 Planificación ↔ 🎯 Detalle` (`setAppMode()`).
- Al entrar en Detalle: se oculta el sidebar de planificación, el mapa se agranda, y aparecen:
  - **Panel izquierdo acoplado** (`#detailLeftDock`): lista de elementos (zona + tramos por tipo).
  - **Panel derecho acoplado** (`#detailRightDock`): Inspector + acciones Lux Studio + resultados.
  - Ambos redimensionables (`_initDockResize`).

**Requisitos del cliente para las fases siguientes:**
- **Todo debe ser editable.**
- Herramientas que permitan variar **luminaria a luminaria** y **por grupos**.
- Selección por **lazo** y otros modos (marquesina, por clase/tipo/potencia).
- **Enviar a Lux Studio** (Excel) e **incorporar el cálculo fotométrico** que devuelve Lux Studio.
  (Intercambio por Excel hoy; API directa en el futuro.)

### Fases pendientes
- **Fase 2 — Motor de selección multi-modo:** clic individual, por tramo, lazo (dibujo libre),
  marquesina (rectángulo), por criterio (clase / tipo de vía / potencia). Acumulativa con Shift/Ctrl.
  Resaltado en mapa sincronizado con lista e inspector.
- **Fase 3 — Edición individual y por lote:** mover/arrastrar luminarias; interdistancia; disposición
  (unilateral/bilateral/tresbolillo/pareado); potencia, tilt, altura, brazo. Inspector edita la
  selección activa; si es grupo, edición en lote. Persistencia en BD.
- **Fase 4 — Integración Lux Studio + visualización:** exportar plantilla Excel de la selección/zona;
  importar resultados (Em, Uo, Ui, cumple); visualizar cumplimiento en el mapa (color por tramo).
  Preparar para futura API directa.

---

## 6. Puntos de anclaje en el código (para localizar rápido)

### `SALVI GIS.html`
- Conmutador de modo (HTML): buscar `class="mode-switch"` (en `<header>`).
- Paneles acoplados (HTML): `id="detailLeftDock"` / `id="detailRightDock"` dentro de `<div class="main">`.
- CSS de docks/switch: buscar `.mode-switch` y `.detail-dock`.
- Lógica de modo: `function setAppMode(` y `function renderDetailDocks(`.
- Resize de docks: `function _initDockResize(`.
- Tabs planificación: `function setTab(`, `function renderZoneDetail(`.
- Selección de zona: `function selectZone(`.
- Carga de datos: `function loadZonesFromAPI(`.
- Config tipos de vía (colores/anchos/spacing): `const ROAD_CFG = {`.
- Auth: `let _authToken`, `function _authHdr(`, `function _doLogin(`, `function _showLogin(`, `_initAuth`.
- Export/import Lux Studio: `exportPlantillaLuminotecnica(`, `importPhotometricResults(`.
- i18n: `function t(`, objeto `STRINGS` (ES/EN/PT/FR/CA); claves nuevas: `mode.planning`, `mode.detail`, `detail.elements`, `detail.inspector`.
- Datos en memoria por zona: `inventoryLuminaires{}`, `zoneData{}` (`.ways`), `zonePhotometric{}`.

### `api_server.py`
- Rutas: buscar la tabla de rutas (regex → handler). Handlers zonas: `h_zones`, `h_zone_create`…
- Export/import: `/api/export/plantilla_luminotecnica`, `/api/import/photometric`, `/api/export/dxf`.
- Auth: `h_auth_login`, `h_auth_me`, `h_auth_setup`, `h_auth_reset_request/apply`.
- Usuarios: `h_users_list/create/update/delete`.
- Árboles: `h_zone_trees_get/put`.
- Consulta libre (IA): `h_db_query` (solo SELECT).

---

## 7. Gotchas y notas de entorno

- **OneDrive + sync:** la carpeta del proyecto está sincronizada. La BD grande (~280 MB) puede
  quedar "solo en la nube"; los procesos que abren rutas pueden fallar hasta que se descargue.
  La corrupción de la BD live vino por aquí — mantener la copia de seguridad al día.
- **No editar `api_server.py` con reemplazos enormes de una sola vez** (riesgo de truncado). Editar por bloques.
- **Emojis vs iconos:** pendiente sustituir emojis por Lucide Icons (tarea de estilo).
- **Italiano (IT):** pendiente añadir como 6º idioma (UI + ayuda).

---

## 8. Tareas pendientes (resumen)

- [ ] Fase 2 — Motor de selección multi-modo (Modo Detalle).
- [ ] Fase 3 — Edición individual y por lote (Modo Detalle).
- [ ] Fase 4 — Integración Lux Studio + visualización de resultados.
- [ ] Añadir italiano (IT): UI strings + sección de ayuda.
- [ ] Sustituir emojis por Lucide Icons.
