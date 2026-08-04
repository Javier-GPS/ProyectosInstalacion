# SALVI Solar Studio — Estado del Proyecto
> Actualizado: julio 2026

---

## Descripción general

Aplicación web de cálculo de alumbrado solar autónomo para productos Salvi Lighting. React 18 + Vite SPA (puerto 5173) con backend Flask Python (puerto 5001). Sustituye a la versión HTML monolítica anterior (`SALVI Solar.html`).

**Arranque:** `arrancar_salvi_solar.bat` → `http://localhost:5173`

---

## Arquitectura

```
Solar/
├── frontend/
│   ├── src/
│   │   ├── App.jsx                      # Root + layout
│   │   ├── context/AppContext.jsx        # Estado global (useReducer)
│   │   ├── utils.js                     # Funciones solares, timezone, formateo
│   │   ├── components/
│   │   │   ├── MainCanvas.jsx           # Router de canvases por step
│   │   │   ├── LeftPanel.jsx            # Panel izquierdo (formularios por step)
│   │   │   ├── TopBar.jsx / BottomBar.jsx
│   │   │   ├── steps/                   # Formularios del panel izquierdo
│   │   │   │   ├── Step1Proyecto.jsx
│   │   │   │   ├── Step2Fotometria.jsx  # Selector vía OSM + cálculo EN 13201
│   │   │   │   ├── Step3PerfilNocturno.jsx
│   │   │   │   ├── Step5Candidatos.jsx
│   │   │   │   ├── Step6Simulacion.jsx
│   │   │   │   ├── Step7Resultados.jsx
│   │   │   │   ├── Step8Detalle.jsx
│   │   │   │   └── Step9Informe.jsx
│   │   │   └── canvas/                  # Vistas del canvas derecho
│   │   │       ├── CanvasStep1.jsx      # Mapa Leaflet de ubicación
│   │   │       ├── CanvasViaEstimacion.jsx  # Mapa para selección de vía
│   │   │       ├── CanvasStep3.jsx      # Gráfico dimming nocturno SVG
│   │   │       ├── CanvasSolarIrradiance.jsx  # Curvas de irradiancia por panel
│   │   │       ├── CanvasSimulacion.jsx
│   │   │       ├── CanvasResultados.jsx
│   │   │       ├── CanvasDetalle.jsx    # KPIs + modal TCO
│   │   │       └── CanvasWelcome.jsx
├── api_server.py                        # Flask API
├── modules/
│   ├── via.py                           # Cálculo fotométrico EN 13201
│   ├── pvgis.py                         # Fetch PVGIS + irradiancia mensual
│   ├── bateria.py                       # Motor batería + tracking SOC
│   └── ...
└── photometric_engine/
    └── ldt/                             # Archivos LDT de ópticas Salvi
```

---

## Decisiones de diseño tomadas

### Arquitectura general

| Decisión | Elección | Motivo |
|----------|----------|--------|
| Frontend | React 18 + Vite | Componentización, hot-reload, mejor DX que HTML monolítico |
| Estado global | `useReducer` + Context | Sin librerías externas, suficiente para la complejidad actual |
| Comunicación | REST `/api/*` | Flask como backend, proxy Vite en dev |
| Mapas | Leaflet | Ligero, sin API key, compatible con OSM |
| Gráficos | SVG inline (custom) | Control total, sin bundler de gráficos pesado |
| Estilos | CSS variables Salvi Design System | Coherencia con otros módulos de la suite |

### Flujo de pasos (Steps)

1. **Proyecto** — nombre, país, coordenadas (mapa Leaflet con picker)
2. **Fotometría** — tipo de vía OSM, clase luminotécnica EN 13201, cálculo potencia
3. **Perfil nocturno** — editor dimming gráfico interactivo SVG
4. **Entorno** — curvas de irradiancia solar por tipo de panel (nuevo)
5. **Candidatos** — selección de productos Salvi
6. **Simulación** — cálculo completo con motor PVGIS + batería
7. **Resultados** — tabla comparativa de candidatos
8. **Detalle** — KPIs del producto seleccionado + modal TCO
9. **Informe** — generación PDF/Word

### Fotometría (Step 2)

- **Fuente de datos de vía:** OpenStreetMap via `/api/road` (Overpass API backend)
- **Clases luminotécnicas:** EN 13201 (ME1–ME6, CE0–CE5, S1–S6) — no la nomenclatura M1–M6 anterior
- **Mapeo highway→clase:** motorway→ME1, secondary→ME3a, residential→ME5, etc. (mirroring `via.py`)
- **Disposición luminarias:** calculada automáticamente por ratio w/H (unilateral / tresbolillo / bilateral / mediana)
- **Ópticas:** f151, f2md, f2m2 con tablas CU reales de archivos LDT
- **Potencia:** auto-sincronizada al cambiar cualquier parámetro → `photometry.system_power_w` en AppContext

### Perfil nocturno (Step 3)

- **Estado compartido del mes** (`npMonth`) en AppContext — sincronizado entre panel izquierdo y canvas
- **Tiempo solar → hora civil local:** `solarToLocalOffset(country, lon, month)` con tabla de zonas horarias y DST por país
- **Eje X:** horas reales locales (encendido/apagado con offsets configurables)
- **Eje Y triple:** % dimming (izq), W potencia (dcha col1, azul), lux (dcha col2, naranja)
- **Interacción:** handles SVG arrastrables para ajustar dimming y segmentos temporales

### Irradiancia solar por tipo de panel (Step 4)

- **Modelo:** cielo despejado, G_DNI=800 W/m², G_diffuse=100 W/m²
- **Tipos calculados:**
  - Horizontal (tilt=0°): G ∝ sin(α)
  - Cilíndrico vertical (SIL): G = G_DNI × 2cos(α)/π + G_dif×0.5
  - Inclinado óptimo (tilt=lat): ángulo óptimo estacional
  - Vertical sur (tilt=90°): referencia
- **Selector de mes:** chips, comparte estado con perfil nocturno (`npMonth`)
- **Métricas:** Wh/m²/día y W/m² pico por tipo de panel

### Mapa vía (Step 2)

- **Selector de capa:** Callejero (OSM), Satélite (ESRI), Terreno (OpenTopoMap) — sin API key
- **Buscador Nominatim:** sobre el botón "Seleccionar vía" → `flyTo` en mapa
- **Nombre de vía** mostrado como card destacado (primer dato del panel)
- **Refresh completo** al seleccionar nueva vía (sin valores stale de OSM)

### TCO y costes

- **Modal detalle TCO** en `CanvasDetalle.jsx` (click en KPI card)
- **CAPEX breakdown:** panel, batería, controlador, estructura, instalación, nodo Smartec, sensor
- **OPEX 10 años:** limpieza, mantenimiento, reemplazo batería, energía red

### Backend (api_server.py)

- **`/api/road`:** consulta OSM (Overpass), devuelve highway, ancho, carriles, nombre + lentes LDT
- **`/api/calculate`:** motor PVGIS + batería + pérdidas; devuelve `capex_breakdown` y `tco_breakdown`
- **`/api/climate`:** fetch PVGIS MRcalc mensual por lat/lon
- **`/api/climate/grid`:** heatmap geográfico (fetch paralelo)

---

## Estado actual — Funcionando

- [x] Motor PVGIS + batería end-to-end
- [x] Árbol de pérdidas + escenarios (recomendado / bajo CAPEX / máx fiabilidad)
- [x] Cálculo fotométrico por vía EN 13201 (via.py + /api/road)
- [x] Editor dimming nocturno interactivo (SVG)
- [x] Perfil nocturno con hora civil local + DST por país
- [x] Eje Y triple (%, W, lux) en gráfico dimming
- [x] Auto-sincronización potencia calculada → AppContext
- [x] Selector de capa mapa (callejero/satélite/terreno)
- [x] Buscador Nominatim + flyTo
- [x] Modal TCO detallado (CAPEX + OPEX)
- [x] Panel Smartec Intelligence + slider SOC objetivo
- [x] Rastreo SOC al anochecer + noches de protección (bateria.py)
- [x] Escalado modular (×N unidades)
- [x] Curvas de irradiancia diaria por tipo de panel (nuevo)

---

## Pendiente / En progreso

### Alta prioridad

- [ ] **Step 4 Entorno:** formulario del panel izquierdo (temperatura ambiente, soiling, factor red) — solo hay canvas
- [ ] **Verificar Step 4** integrado en LeftPanel.jsx con selector step=4
- [ ] **Pruebas integración** React SPA completo (steps 1–9 end-to-end)
- [ ] **Launcher bat actualizado** para nueva arquitectura Vite+Flask

### Funcionalidades pendientes

- [ ] **Irradiancia difusa mensual** en gráfico de curvas (actualmente solo clear-sky)
- [ ] **Datos reales PVGIS** en curvas diarias (por ahora modelo analítico simplificado)
- [ ] **Perfil de carga diario** superpuesto con curva de consumo vs generación
- [ ] **Exportación informe** (PDF/Word) desde nuevo React SPA
- [ ] **Heatmap climático** (mapa Leaflet con overlay kWh/m²) en nueva SPA
- [ ] **GIS Import** modal migrado a nueva SPA
- [ ] **Modo oscuro** (variables CSS preparadas, falta toggle)

### Bugs conocidos

- [ ] Estado OSM (vía importada) no persiste al navegar entre pasos (estado local de `Step2Fotometria`)
- [ ] `Step5Candidatos` no tiene canvas dedicado (muestra welcome)
- [ ] En Git sobre OneDrive → error `index.lock` — usar ZIP para backups

### Integraciones Salvi Suite

- [ ] **Salvi GIS:** importar tendido viario desde GIS a Solar
- [ ] **Salvi LUX:** intercambio de productos y fotometría
- [ ] **Smartec:** configuración nodo desde Solar (API Smartec pendiente)

---

## Valores de referencia

### Husos horarios implementados

| País | Std | DST | Período DST |
|------|-----|-----|-------------|
| ES, FR, DE, IT | UTC+1 | UTC+2 | Mar–Oct |
| PT | UTC+0 | UTC+1 | Mar–Oct |
| MA, DZ, TN, NG | UTC+1 | — | Sin DST |
| EG | UTC+2 | — | Sin DST |
| KE | UTC+3 | — | Sin DST |
| ZA | UTC+2 | — | Sin DST |
| SA | UTC+3 | — | Sin DST |
| IN | UTC+5:30 | — | Sin DST |
| BR | UTC-3 | UTC-2 | Oct–Feb (hem. sur) |
| MX | UTC-6 | UTC-5 | Mar–Oct |

### Clases luminotécnicas EN 13201

| Highway OSM | Clase | Lux mínimos |
|-------------|-------|-------------|
| motorway / trunk | ME1 | 30 lux |
| primary | ME2 | 15 lux |
| secondary | ME3a | 10 lux |
| tertiary | ME4a | 7.5 lux |
| residential | ME5 | 5 lux |
| living_street | S2 | 10 lux |

---

## Archivos de backup

- `BACKUP_20260716_0836.zip` — backup pre-migración React SPA
- `SALVI Solar.html` — versión HTML monolítica anterior (referencia)
- `CLAUDE.md` (en carpeta CALCULO FOTOMETRICO SALVI) — contexto módulo túneles
