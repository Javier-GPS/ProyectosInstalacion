# SALVI Tunnel Engine — Contexto de proyecto

Módulo de cálculo de iluminación de túneles integrado en LuxStudio (app propia de Salvi, alternativa a DIALux). Flask + React SPA inline con Babel. Arrancar: `arrancar_tunnel.bat` → `http://localhost:5000/tunnel`.

---

## Arquitectura general

```
CALCULO FOTOMETRICO SALVI/
├── app.py                          # Flask, todas las rutas API
├── templates/tunnel.html           # React SPA (~4600 líneas, Babel inline, Leaflet, Recharts)
├── modules/tunnel/
│   ├── engine.py                   # Orquestador CIE 88:2004
│   ├── zones.py                    # Zonas bidireccionales asimétricas (Umbral/Transición/Interior)
│   ├── profile.py                  # Perfil longitudinal de luminancias
│   ├── luminaires.py               # Diseño APHEX inside-out, tilt_overrides
│   ├── photometric_verify.py       # Wrapper CIE 140 — U0/Ul/TI por zona + radiosidad
│   ├── control.py                  # Control DALI (curva dimming continua)
│   ├── report.py                   # Informe Word (python-docx)
│   └── excel_export.py             # Exportación Excel
└── photometric_engine/
    └── salvi_photometry/
        ├── ldt_parser.py           # Parser de archivos LDT (luminarias APHEX S/M/L)
        ├── rtables.py              # R-tables CIE 144 (R1/R2/R3/C1/C2)
        ├── geometry.py             # Geometría de cálculo
        ├── calculator.py           # Motor CIE 140:2019 — luminancias directas
        └── radiosity.py            # Radiosidad Gauss-Seidel (TunnelSection, Patch, solve_radiosity)
```

---

## Features implementadas

### Cálculo CIE 88:2004
- L20 → Lseq → Lth para zonas Umbral, Transición, Interior
- Perfil longitudinal de luminancias
- **Bidireccional asimétrico**: Portal B usa orientación opuesta → Lth_b diferente → zonas y perfil asimétricos
- Escalones de transición configurables

### Luminarias APHEX S / M / L
- Diseño inside-out por zonas (desde Interior hacia portales)
- Tilt por zona, overrides manuales en tabla editable
- Marcadores en mapa: color por modelo (S=verde #22c55e, M=azul #3b82f6, L=violeta #a855f7)
- Tooltip con W / mA / interdistancia / tilt / Lreq

### Verificación fotométrica CIE 140:2019
- U0 / Ul / TI por zona usando LDT + r-tables
- **Modo Directo** (⚡): fórmula CIE 140 pura
- **Modo Radiosidad** (✦): interreflexión difusa paredes/techo/pavimento
  - Inputs ρ Paredes (default 0.40) y ρ Techo (default 0.25) en panel Geometría
  - Gauss-Seidel iterativo en `radiosity.py`
  - Columna L ind. (%) en tabla de resultados
  - Banner azul mostrando ρ activos

### UI / UX
- Wizard 6 pasos: Geometría → Entorno → Tráfico → Luminarias → Control → Resultados
- Mapa Leaflet con importación de túneles desde OpenStreetMap (Overpass API proxied por Flask)
- "Ver en mapa" desde fase Luminarias → navega a Entorno con overlay activo
- ErrorBoundary React: crashes de render → "Reintentar" en lugar de pantalla blanca
- Multi-tubo T1/T2
- Informe Word, Excel, control DALI

---

## Rutas API principales (app.py)

| Ruta | Método | Función |
|------|--------|---------|
| `/tunnel` | GET | Sirve tunnel.html |
| `/api/tunnel/calculate` | POST | Motor CIE 88 completo |
| `/api/tunnel/luminaires` | POST | Diseño luminarias + verificación CIE 140/radiosidad |
| `/api/tunnel/report` | POST | Genera Word .docx |
| `/api/tunnel/export-excel` | POST | Genera .xlsx |
| `/api/overpass` | POST | Proxy Overpass OSM |

---

## Reglas críticas — LEER ANTES DE EDITAR

### ⚠️ OneDrive + Edit tool trunca archivos
**Nunca usar la herramienta Edit directamente sobre archivos en la carpeta OneDrive.**  
Siempre usar scripts bash Python con `f.write(content)` completo:

```bash
python3 << 'PYEOF'
path = '/sessions/.../mnt/CALCULO FOTOMETRICO SALVI/templates/tunnel.html'
with open(path,'r',encoding='utf-8') as f: src = f.read()
# modificaciones sobre src
with open(path,'w',encoding='utf-8') as f: f.write(src)
PYEOF
```

### ⚠️ app.py debe tener bloque `__main__`
```python
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
```
Sin él, `python app.py` importa y sale sin arrancar Flask.

### ⚠️ tilt_overrides en app.py
En la ruta `/api/tunnel/luminaires`, `tilt_overrides` viene en el top-level de `data`, no dentro de `luminaire`. Se extrae explícitamente:
```python
luminaire_params['tilt_overrides'] = data.get('tilt_overrides', {}) or {}
```

### ⚠️ tunnel.html es React con Babel inline
No es JSX compilado. Todo en un solo fichero HTML. Los cambios de string deben ser exactos en indentación. Usar `assert OLD in src` antes de reemplazar para detectar fallos a tiempo.

### ⚠️ Gráfica longitudinal Lavg
La curva roja solo puede construirse con `photometric.real_profile`: un valor
`Lavg` por campo bidimensional CIE 140 entre luminarias consecutivas. Nunca
usar como fallback `L_est`, `L_req` ni puntos individuales de la lista de
luminarias, porque las capas solapadas producen dientes verticales sin
significado normativo. Si falta el perfil CIE 140, mostrar un aviso y solicitar
recálculo.

### ⚠️ Posición transversal de luminarias
`wall_offset_m` es la coordenada desde la pared izquierda y
`axis_offset_m = W/2 - wall_offset_m`. En `central_offset` la fila está en
`y=wall_offset_m`; en `central_double`, en
`y=[wall_offset_m, W-wall_offset_m]`. El cálculo, la verificación, la sección,
la planta, la tabla, el 3D y el mapa deben usar exactamente estas coordenadas.

---

## Estado actual (julio 2026)

**Completado y funcionando:**
- CIE 88 + CIE 140 end-to-end
- Radiosidad integrada (directo + interreflexión)
- Inputs ρ Paredes / ρ Techo con tooltip InfoTip (hover → tabla de valores típicos)
- Tilt overrides funcionando correctamente en U0/Ul
- OSM import robusto (try/catch, filtro null)
- Marcadores mapa con colores por modelo

**Bugs conocidos / limitaciones:**
- Estado OSM (túnel importado) no persiste al navegar entre fases (estado local de MapSelector)
- Git en OneDrive da error de `index.lock` → usar ZIP para backups

**Backup:** `BACKUP_20260716_0836.zip` en carpeta del proyecto

---

## Valores de referencia

### Reflectancias típicas en túneles (ρ = reflectancia, NO absorción)
| Superficie | Limpio | Explotación | Muy sucio |
|-----------|--------|-------------|-----------|
| Paredes hormigón | 0.50–0.65 | 0.20–0.40 | 0.10–0.20 |
| Techo hormigón | 0.25–0.45 | 0.05–0.20 | 0.03–0.10 |
| Pavimento asfalto oscuro | 0.07 | — | — |
| Pavimento hormigón | 0.28 | — | — |

### Luminarias APHEX (lúmenes por W nominal)
- Aphex S: fichero LDT en `photometric_engine/ldt/`
- Aphex M: ídem
- Aphex L: ídem

---

## Cómo iniciar una sesión nueva con este fichero

1. Abre un chat nuevo en Cowork
2. Adjunta o pega el contenido de este `AGENTS.md`
3. Di: "Continuamos el proyecto SALVI Tunnel Engine, lee el AGENTS.md adjunto"
4. El modelo tendrá contexto completo sin historial ruidoso

## Imported Claude Cowork project instructions
