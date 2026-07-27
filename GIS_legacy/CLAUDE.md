# SALVI GIS — Guía del proyecto (para Claude Code)

> Este archivo lo lee Claude Code automáticamente al abrir la carpeta. Contiene todo el
> contexto, arquitectura, instrucciones y el plan de trabajo pendiente.
> Reemplaza a `HANDOFF.md` (puedes borrar ese). Última actualización: 2026-07-21.

---

## 1. Qué es

Herramienta web de **análisis y diseño de alumbrado público urbano**. Carga datos reales de
OpenStreetMap (OSM), clasifica la red viaria, calcula necesidades de iluminación según **EN 13201**
y exporta inventario de luminarias + plantillas para cálculo fotométrico (Lux Studio).

Proyectos activos: Angola, Mauritania, Senegal, Egipto, Rwanda, Benín, España.

### Dos fases de trabajo (concepto central del producto)

1. **Planificación / estimación preliminar** — desde una zona se buscan calles OSM, se aplican
   valores por defecto (clase lumínica, interdistancia…) y se estiman rangos de proyecto para
   presentar a cliente/político. Vista *maestra* sobre muchas zonas. **Ya funciona bien.**

2. **Detalle / replanteo** — sobre una zona concreta se editan posiciones de luminarias,
   interdistancias y disposiciones, se envía a **Lux Studio** (Excel; API directa en el futuro) y
   se importan los resultados fotométricos para visualizar cumplimiento en el mapa.
   **Completo (Fases 1-4, ver §8).** Modo conmutable con paneles acoplados: selección multi-modo,
   edición individual/por lote persistida en BD, y visualización de cumplimiento sobre el mapa.

---

## 2. Stack y ejecución

- **Frontend:** un único fichero `SALVI GIS.html` (~11.000 líneas): HTML + CSS + JS inline. Mapa **MapLibre GL JS 4.7.1** (CDN unpkg). Sin build, sin framework.
- **Backend:** `api_server.py` — Python **solo stdlib** (`http.server`), sin dependencias de framework. Puerto **8733**. Requiere `ezdxf` y `openpyxl` (se instalan solos vía el .bat).
- **BD:** SQLite en `db/salvi_gis.db`.
- **Servidor estático:** `python -m http.server 8732` sirve el HTML.

### Arrancar
```bash
python fix_db.py         # SOLO si la BD está dañada o falta el usuario (ver §5)
# Windows: doble clic en "Abrir SALVI GIS.bat"  (mata puertos, arranca todo, abre Chrome)
# Manual:
python api_server.py                 # backend  → http://localhost:8733
python -m http.server 8732           # frontend → http://localhost:8732/SALVI GIS.html
```

### Reglas de edición
- **NO reemplazar bloques enormes de `api_server.py` de una sola vez** — una edición grande ya lo
  truncó una vez (se perdió el final del fichero). Editar por bloques pequeños y verificar con
  `python -c "import ast; ast.parse(open('api_server.py').read())"`.
- El HTML es gigante: usar búsquedas por anclas (§7) en vez de leerlo entero.

---

## 3. Ficheros

| Fichero | Rol |
|---|---|
| `SALVI GIS.html` | Frontend completo (HTML+CSS+JS). |
| `api_server.py` | Backend HTTP + SQLite (~1.560 líneas). |
| `db/salvi_gis.db` | BD SQLite viva. |
| `db/salvi_gis - copia.db` | Copia de datos (⚠️ SIN tabla `users`). |
| `fix_db.py` | Repara BD desde la copia + crea/resetea usuario admin. |
| `reset_password.py` | Gestión de usuarios por CLI (`--list`, `--reset USER`, `--create`, `--delete USER`). |
| `Abrir SALVI GIS.bat` | Lanzador Windows. |
| `.env` | `AUTH_SECRET`, `ANTHROPIC_API_KEY`, `SMTP_*` opcional. **No commitear.** |
| `fonts/` | Fuentes de marca Exposure (205TF). |

---

## 4. Modelo de datos (esquema SQLite)

- **projects**(id, name, created_at)
- **zones**(id, name, type, color, priority, center_lat, center_lon, zoom, bbox, description,
  est_primary, est_secondary, est_tertiary, est_residential, est_unclassified,
  corridors[JSON], bounds_polygon[JSON], osm_relation, source, created_at, project_id)
- **zone_config**(zone_id, spacing, watt_hps, watt_led, efficacy, hours_night, updated_at)
- **zone_osm_data**(zone_id, km_by_type[JSON], ways[JSON], source, loaded_at) — `ways` guarda los
  tramos OSM y, dentro de cada way, `luxParams` (parámetros por tramo para Lux Studio).
- **luminaires**(id, project_id, zone_id, road_type, lighting_class, street_name, lat, lon, watts,
  spacing, placed_at, tilt, height_m, arm_len, distribution) — luminarias **diseñadas/colocadas**.
  Las 4 últimas columnas (Fase 3, override por luminaria individual) se rellenan vía
  `collectLuminairePositions`/`_lumFieldValue`; si no hay override, viajan con el valor por defecto
  del tramo (`luxParams` / fórmula de watts).
- **inventory_luminaires**(id, zone_id, point_id, lat, lon, power_w, height_m, brand, model,
  lamp_type, support_type, circuit_id, line_id, extra[JSON], way_key, road_type, imported_at) — inventario de campo.
- **photometric_results**(id, zone_id, segment_name, match_key, road_width, spacing, lighting_class,
  power_w, lm_em, uo, ui, ti, sr, model, lente, tilt, phi_lm, cumple, notes, imported_at) — resultados de Lux Studio.
- **project_ui_config**(project_id, config_key, config_value[JSON], updated_at)
- **zone_trees**(zone_id, trees[JSON], loaded_at) — árboles OSM.
- **users**(id, username, email, password_hash, role, active, created_at, last_login)

`init_db()` crea tablas con `CREATE TABLE IF NOT EXISTS` (nunca borra datos). Migraciones idempotentes en `_MIGRATIONS`.

---

## 5. Autenticación

- JWT **HS256** firmado con `AUTH_SECRET` (persistido en `.env`, estable entre reinicios).
- Token en `localStorage['_salvi_token']`; cabecera `Authorization: Bearer <token>`.
- TTL 7 días (30 si "Recordarme"). Password: **PBKDF2-SHA256, 600k iteraciones**, salt 32 bytes.
- Rutas públicas: `/api/auth/login`, `/api/auth/setup`. Resto exige token.
- Recuperación por token (in-memory, 1h). SMTP opcional; si no, el admin copia el código.

### ⚠️ Gotcha crítico (causa de 401 masivos)
Si se **reconstruye la BD** (restaurar copia + recrear usuario con `fix_db.py`), el **uid del
usuario cambia**. Los tokens antiguos guardados en el navegador apuntan a un uid inexistente →
**401 en todos los endpoints**. **NO es pérdida de datos.** Solución: cerrar sesión y volver a
entrar, o `localStorage.clear()` + recarga.

---

## 6. API REST (rutas → handler en `api_server.py`)

**GET**
`/api/auth/me` · `/api/users` · `/api/nominatim/search` · `/api/nominatim/reverse` · `/api/projects` ·
`/api/zones` · `/api/zones/osm/all` · `/api/zones/{id}/osm` · `/api/zones/{id}/inventory` ·
`/api/zones/{id}/trees` · `/api/zones/{id}/photometric` · `/api/luminaires` ·
`/api/projects/{id}/ui-config` · `/api/luminaires/export` · `/api/export/dxf`

**POST**
`/api/auth/login` · `/api/auth/setup` · `/api/auth/reset-request` · `/api/auth/reset-apply` ·
`/api/users` · `/api/projects` · `/api/zones` · `/api/luminaires/bulk` ·
`/api/export/plantilla_luminotecnica` · `/api/parse/inventory_excel` · `/api/import/inventory` ·
`/api/import/photometric` · `/api/ai/ask` · `/api/db/query` (solo SELECT)

**PUT**
`/api/users/{id}` · `/api/projects/{id}/ui-config` · `/api/zones/{id}/trees` · `/api/zones/{id}/osm` ·
`/api/zones/{id}/config` · `/api/zones/{id}`

**DELETE**
`/api/users/{id}` · `/api/projects/{id}` · `/api/zones/{id}` · `/api/luminaires/{zone}/{id}`

El dispatch está en `Handler._dispatch` (tabla regex→método). El usuario autenticado queda en `self._current_user`.

---

## 7. Anclas de código (buscar estas cadenas)

### `SALVI GIS.html`
- Mapa init: `new maplibregl.Map(` — estilo, centro, zoom, pitch.
- Modos vista base / terreno 3D: `_ensureRasterSource`, `setTerrain`, `_base-sat`, `_src-dem`.
- **Modo conmutable** (Fases 1-4 hechas, ver §8): HTML `class="mode-switch"`, `id="detailLeftDock"`, `id="detailRightDock"`; CSS `.mode-switch` / `.detail-dock`; JS `function setAppMode(`, `function renderDetailDocks(`, `function _initDockResize(`.
- **Selección multi-modo Detalle** (Fase 2): `let detailSelectionMode`, `let selectedLumIds`, `function setDetailSelectionMode(`, `toggleLumSelection(`, `selectLumIds(`, `_refreshSelectionLayer(`, `_onSelectionChanged(`, `applyCriteriaSelection(`, `_armMarquee(`/`_cancelMarquee(`, `lassoPurpose`.
- **Edición individual/lote Detalle** (Fase 3): `_lumFieldValue(`, `_defaultWatts(`, `applyBatchLumField(`, `applyGroupLumField(`, `_scheduleDetailAutoSave(`, `_detailDragState` (arrastre de 1 punto seleccionado).
- **Cumplimiento Lux Studio** (Fase 4): `_cumpleStatus(`, `_buildComplianceFeatures(`, `_updateComplianceLayer(`, `toggleComplianceLayer(`, capa `compliance-{zoneId}`.
- Tabs planificación: `function setTab(`, `function renderZoneDetail(`, `function renderAnalysis(`.
- Selección de zona: `function selectZone(`, `function showAllZones(`.
- Reconstrucción de capas de zona en mapa: `function _rebuildZoneLayers(`, `function _rebuildAllMapLayers(`.
- Carga de datos: `function loadZonesFromAPI(`, `function switchProject(`.
- Config tipos de vía (colores/anchos/spacing/defaults): `const ROAD_CFG = {`.
- Clases lumínicas EN 13201: `LIGHTING_CLASS_MAP`, `LAMP_EFFICACY`.
- Auth: `let _authToken`, `function _authHdr(`, `function _doLogin(`, `function _showLogin(`, `_initAuth`, `function _doForgot(`, `function _doReset(`.
- Lux Studio: `exportPlantillaLuminotecnica(`, `importPhotometricResults(`, `getPhotometric(`, `_wayForKey(`, `PLANTILLA_DEFAULTS`.
- Inventario en mapa: `function _updateInventoryLayer(`, `inventoryLuminaires{}`.
- i18n: `function t(`, objeto `STRINGS` (ES/EN/PT/FR/CA). Claves del modo: `mode.planning`, `mode.detail`, `detail.elements`, `detail.inspector`.
- Globals por zona: `inventoryLuminaires{}`, `zoneData{}` (`.ways`, `.kmByType`, `.source`), `zonePhotometric{}`, `zoneSpacing{}`, `zoneTypeSpacing{}`, `zoneTypeVisibility{}`.
- Estado modo: `let appMode`, `let detailZoneId`, `let selectedZone`, `let activeProjectId`.

### `api_server.py`
- Tabla de rutas: buscar `h_auth_me` (empieza el bloque GET).
- Zonas: `h_zones`, `h_zone_create`, `h_zone_update`, `h_zone_osm`, `h_zone_osm_save`, `h_zone_config`.
- Export/import: `h_export_dxf`, `h_export_plantilla`, `h_import_photometric`, `h_import_inventory`, `h_parse_inventory`.
- Auth: `h_auth_login`, `h_auth_setup`, `h_auth_me`, `h_auth_reset_request`, `h_auth_reset_apply`.
- Usuarios: `h_users_list/create/update/delete`.
- Árboles: `h_zone_trees_get/put`. IA: `h_ai_ask`, `h_db_query`.
- Helpers: `_jwt_make/_jwt_verify`, `_hash_pw/_verify_pw`, `_format_zones`, `_build_project_context`.

---

## 8. Modo Detalle — HECHO (Fases 1-4)

Decisión del cliente: **modo conmutable** (no ventana aparte). Requisitos cumplidos:
- **Todo editable.**
- Variar **luminaria a luminaria** y **por grupos**.
- Selección por **lazo** y otros modos (marquesina, por clase/tipo/potencia). Acumulativa Shift/Ctrl.
- **Enviar a Lux Studio** (Excel) e **importar** su cálculo fotométrico. (API directa queda para el futuro.)

### ✅ Fase 1 — Conmutador y paneles
`🗺 Planificación ↔ 🎯 Detalle` en la cabecera (`setAppMode`). Al entrar en Detalle: se oculta el
sidebar, el mapa se agranda, aparecen panel izquierdo (`#detailLeftDock`, lista de elementos) y
derecho (`#detailRightDock`, Inspector + acciones Lux Studio + resultados), ambos redimensionables.

### ✅ Fase 2 — Motor de selección multi-modo
Clic individual, clic en tramo (todas sus luminarias), **lazo** (dibujo libre, reutiliza el motor de
`startDraw`/`onLassoEnd` con `lassoPurpose='select'` en vez del modal destructivo de borrar calles),
**marquesina** (rectángulo vía `map.queryRenderedFeatures` en coordenadas de pantalla), y **por
criterio** (tipo de vía / clase lumínica / rango de potencia). Selección acumulativa con Shift/Ctrl
(`selectedLumIds`, Set de ids `wKey__lumIdx`), resaltada en el mapa (capa `selected-lum-{zoneId}`) y
reflejada en panel izquierdo/derecho.

### ✅ Fase 3 — Edición individual y por lote
Inspector editable sobre la selección activa (potencia, tilt, altura, brazo, clase lumínica — override
real **por luminaria individual**, no solo por tramo; interdistancia/disposición — por tramo, ya que
son conceptos geométricos de grupo, regeneran los puntos del tramo afectado). Persistido en BD (tabla
`luminaires`, columnas `tilt`/`height_m`/`arm_len`/`distribution` añadidas vía migración aditiva,
auto-guardado debounced por zona+tipo). Arrastre de un punto individual seleccionado sobre MapLibre
(paralelo al arrastre ya existente de Planificación, sin tocarlo).

### ✅ Fase 4 — Integración Lux Studio + visualización de cumplimiento
Export/import Excel ya existentes (`exportPlantillaLuminotecnica`, `importPhotometricResults` →
`photometric_results`) sin cambios de esquema. Nueva capa `compliance-{zoneId}` (línea, oculta por
defecto, toggle `toggleComplianceLayer`) que colorea cada tramo verde/rojo/gris según el campo
`cumple` importado (texto libre normalizado) con **fallback numérico** Em vs lux requerido de la
clase cuando `cumple` viene vacío. El emparejamiento tramo↔fotométrico es **paramétrico**
(ancho·espaciado·clase, vía `getPhotometric`), no por identidad de tramo — así es como ya funciona el
export/import, es una limitación conocida y documentada, no un bug.

### Nota pendiente (no bloqueante)
Los overrides de Fase 3 persisten en BD pero no hay round-trip de carga: al recargar la página,
`streetLumLayers` (estado en memoria) no se rehidrata desde `/api/luminaires`, solo desde
`placeStreetLuminaires` con los valores por defecto. Si se quiere que las ediciones sobrevivan a un
refresco de página, hace falta implementar esa carga — discutirlo si se convierte en un problema real.

---

## 9. Configuración del mapa 3D (referencia — reutilizable en otras apps)

Todas las fuentes son **gratuitas y sin token**.
- Librería: MapLibre GL JS 4.7.1.
- Estilo base vectorial: `https://tiles.openfreemap.org/styles/liberty`
- Satélite: Esri World Imagery `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`
- Hillshade: Esri `.../Elevation/World_Hillshade_Dark/MapServer/tile/{z}/{y}/{x}`
- **DEM terreno 3D:** AWS Terrain Tiles `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png` — `raster-dem`, `encoding:'terrarium'`, `tileSize:256`, `maxzoom:14`.
- `setTerrain({source, exaggeration:2.0})`, `pitch:50`, fondo canvas `#0d1520`, `setFog(null)`.
- Atribución obligatoria: © OpenStreetMap, Esri, Mapzen/AWS Terrain Tiles.

---

## 10. Otras tareas pendientes
- Añadir **italiano (IT)** como 6º idioma (UI strings + sección de ayuda).
- Sustituir **emojis por Lucide Icons**.

## 11. Gotchas de entorno
- Carpeta en **OneDrive** (sync). La BD grande (~280 MB) puede quedar "solo en la nube"; al abrirla
  puede fallar hasta descargarse. La corrupción previa de la BD vino de aquí — **mantener la copia al día**.
- Verificar sintaxis de `api_server.py` tras cada edición (`ast.parse`).
- Idiomas soportados: ES, EN, PT, FR, CA (IT pendiente).
