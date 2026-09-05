# SALVI Tunnel Engine — Documento de traspaso a Claude Code

> **Propósito**: transferir todo el conocimiento del desarrollo hecho en Cowork
> para continuar el trabajo en Claude Code (CLI). Léelo junto con `CLAUDE.md`
> (contexto de arquitectura base) — este fichero cubre lo que se ha construido
> **encima** de ese estado y lo que queda por hacer.
>
> **Fecha de traspaso**: 17 julio 2026
> **Última sesión Cowork**: features de tándem, ROI paredes reflectantes,
> distancia de parada, y correcciones del optimizador.

---

## 0. Cómo arrancar

```bat
arrancar_tunnel.bat        REM  → http://localhost:5000/tunnel
```

Requiere reiniciar el servidor Flask tras cada cambio en `.py`.
Los cambios en `templates/tunnel.html` (React con Babel inline) sólo requieren
recargar el navegador (F5), **no** reiniciar Flask.

---

## 1. REGLAS CRÍTICAS (heredadas de CLAUDE.md — siguen vigentes)

### ⚠️ OneDrive + herramienta de edición trunca archivos
En Cowork nunca se usó la herramienta `Edit` directa sobre ficheros OneDrive
porque truncaba. **En Claude Code (CLI) este problema NO aplica** — la
herramienta Edit del CLI trabaja sobre disco local normalmente. Aun así, para
`tunnel.html` (fichero de ~270k chars, React+Babel) conviene:
- Verificar con `assert OLD in src` mentalmente antes de reemplazar.
- Hacer reemplazos de strings exactos con indentación idéntica.

### ⚠️ `app.py` debe conservar el bloque `__main__`
```python
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
```

### ⚠️ `tunnel.html` es React con Babel inline (NO JSX compilado)
Todo en un solo fichero HTML. No hay build step. Los ternarios anidados dentro
de strings son una fuente frecuente de bugs (ver §7).

### ⚠️ `tilt_overrides` y `tandem_overrides` llegan en el top-level de `data`
En la ruta `/api/tunnel/luminaires`, NO dentro de `luminaire`. Se extraen
explícitamente en `app.py` (~línea 583):
```python
luminaire_params['tilt_overrides']   = data.get('tilt_overrides', {}) or {}
luminaire_params['tandem_overrides'] = data.get('tandem_overrides', {}) or {}
```

### ⚠️ `Lth_b` debe propagarse en 3 sitios de app.py
`engine.py` calcula `Lth_b` (umbral portal B) en `result['summary']`, pero
`app.py` debe extraerlo explícitamente. Está en las 3 rutas que usan luminarias
(preview ~517, principal ~582, retrofit ~669):
```python
luminaire_params['Lth_b'] = float(result['summary'].get('Lth_b', luminaire_params['Lth']))
```

---

## 2. ARQUITECTURA (recordatorio)

```
CALCULO FOTOMETRICO SALVI/
├── app.py                          # Flask, todas las rutas API
├── templates/tunnel.html           # React SPA (~270k chars, Babel inline)
├── modules/tunnel/
│   ├── engine.py                   # Orquestador CIE 88:2004
│   ├── zones.py                    # Zonas bidireccionales asimétricas
│   ├── profile.py                  # Perfil longitudinal de luminancias
│   ├── luminaires.py               # Diseño APHEX inside-out + TÁNDEM
│   ├── optimizer.py                # Optimizador U0/Ul/L por óptica+tilt
│   ├── photometric_verify.py       # Wrapper CIE 140 + radiosidad
│   ├── control.py                  # Control DALI
│   ├── report.py                   # Informe Word
│   └── excel_export.py             # Exportación Excel
└── photometric_engine/salvi_photometry/
    ├── ldt_parser.py               # Parser LDT (APHEX S/M/L)
    ├── rtables.py                  # R-tables CIE 144
    ├── geometry.py                 # Geometría (Observer, LuminaireOrientation)
    ├── calculator.py               # Motor CIE 140:2019 — luminancias directas
    └── radiosity.py                # Radiosidad Gauss-Seidel
```

### Rutas API (app.py)

| Ruta | Método | Función |
|------|--------|---------|
| `/tunnel` | GET | Sirve tunnel.html |
| `/api/tunnel/calculate` | POST | Motor CIE 88 completo |
| `/api/tunnel/luminaires` | POST | Diseño luminarias + verificación CIE 140/radiosidad |
| `/api/tunnel/report` | POST | Genera Word .docx |
| `/api/tunnel/export-excel` | POST | Genera .xlsx |
| `/api/overpass` | POST | Proxy Overpass OSM |

---

## 3. TRABAJO REALIZADO EN LAS ÚLTIMAS SESIONES

### 3.1 Correcciones del optimizador (CRÍTICO — verificar tras reinicio)

**Problema**: el optimizador subestimaba L en ~50%, comprimía todas las zonas a
`D_MIN` innecesariamente. Ambas bocas mostraban el mismo valor (298 cd/m²) pese
a requisitos distintos (198 vs 312).

**Causas y fixes en `optimizer.py`**:
1. `_build_lums`: usaba `n_periods=5` con `range(5)`. Cambiado a `n_side=5` con
   `range(-5, 6)` → **11 grupos** (± 5 períodos), igual que `photometric_verify`.
2. `_L_array`: `Observer(lane_y_m=w/2)` sin distancia. Cambiado a
   `Observer(lane_y_m=w/2, d_observer_m=60.0)` según **CIE 140 §6.2.2**
   (observador a 60 m adelante).

**Fix relacionado en `luminaires.py`**: `transition_b` usaba `Lth` (portal A)
en vez de `Lth_b` (portal B) para la curva CIE 88. Ahora lee `Lth_b`.

> ⚠️ **PENDIENTE DE VERIFICACIÓN**: confirmar que CTH ya no está sobreiluminado
> (debe encontrar un espaciado > D_MIN para L_req=198, no apilar a D_MIN).

### 3.2 Tabla individual de luminarias (fase Resultados)

Lista por ID con: ID | Zona | Par | x(m) | y(m) | d→ | Modelo | Lente | Tilt |
mA | W | L_req | [Lat | Lon].
- Div scrollable (max-height 320px), header sticky.
- `hasSP = z.setpoints && z.setpoints.length === z.n_luminaires` → usa setpoints
  individuales cuando existen (transiciones y ahora tándem).

### 3.3 Coordenadas GPS en la tabla

Columnas Lat/Lon aparecen sólo si `hasGPS = !!(form.lat && form.lng)` (portal
fijado en el mapa). Cálculo con haversine `_moveAlong(lat,lng,dist,bearing)` +
desplazamiento transversal perpendicular. Bearing del octante `form.portal_orientation`.

### 3.4 Overlay CIE 88 vs CIE 140 en gráfico longitudinal

`TunnelLuminanceLayout({ result, lumResult, photoResult })`. Curva requerida
CIE 88 (azul) + curva medida CIE 140 por zona (verde `#059669`, escalonada).
`measPts` construido de `photoResult.zones` matcheado a posiciones de zona.

### 3.5 Fix warning banner + Estado CIE 140

- Banner cruza `photoResult.zones` (CIE 140 real) en vez de `L_estimated`
  (estimación optimizador). Etiqueta "(CIE 140)" o "(estimación opt.)".
- Tabla CIE 140: nueva columna `L_req` y check `lok = Lreq<=0 || L_avg>=Lreq*0.95`.
  Filas no conformes con fondo `#fff5f5`. Estado ahora contempla L_avg vs L_req
  (antes sólo miraba U0/Ul/TI).

### 3.6 Panel ROI paredes reflectantes (fase Resultados)

Sólo visible en **modo Radiosidad** (`photoResult.calc_mode==='radiosity'`).
- Detecta zonas con `L_avg > L_req` gracias al aporte indirecto → ahorro
  potencial por dimming DALI.
- Superficie tratada = paredes + techo (sin pavimento), según forma del túnel.
- 3 inputs: coste energía (€/kWh), horas/año, coste tratamiento (€/m²).
- 4 KPIs: reducción W, ahorro €/año, inversión, retorno simple (años).
- Estado `roi` en `LuminaireSectionEditor`: `{kwhCost, hoursYear, treatCostM2, open}`.

### 3.7 Distancia y tiempo de parada (fase Tráfico / Geometría)

Card "🛑 Distancia y tiempo de parada — CIE 88:2004 §4.1" en `StepTraffic`.
- Inputs: μ (auto por velocidad, editable) y t_reacción (default 2.5 s).
- Fórmula: `d = v·t_r + v²/(2g·(μ − i))` donde i = pendiente/100 (bajada empeora).
- KPIs: distancia de parada, tiempo de parada, longitud mínima zona umbral (=d_parada).
- Campos nuevos en `DEFAULT_FORM`: `mu_friction:null, t_reaction:2.5`.

### 3.8 Modo TÁNDEM (2 luminarias por posición) — Opción C ⭐ ÚLTIMA FEATURE

**Motivación**: cuando el tamaño físico de la luminaria supera la distancia
mínima de espaciado, se colocan 2 luminarias una tras otra ("tándem"). El
espaciado entre PARES es normal, pero cada posición lleva doble flujo.

**Decisión de diseño confirmada con el usuario**:
- `n_luminaires` = **físicas por lado** (no "grupos"). No existe concepto de grupo
  en el código; `n_luminaires` siempre fue el recuento físico.
- Con tándem: `n_luminaires` pasa de `n_posiciones` a `2 × n_posiciones`.
- `d_used` = espaciado entre **centros de par** (inter-par, el dominante).
- `n_tandem` (1 o 2) = campo informativo para la UI.
- `tandem_offset_m` = separación física del par (= largo del cuerpo del modelo).

**Backend `luminaires.py`**:
- `_BODY_LEN = {"S": 0.50, "M": 0.70, "L": 1.00}` (metros).
- `ZoneLuminaireDesign` + campos `n_tandem` y `tandem_offset_m` (+ en `to_dict()`).
- `_design_zone_aphex(..., tandem_override: Optional[bool] = None)`:
  - `None` = auto, `True` = forzar tándem, `False` = forzar individual.
  - Autodetección uniforme: `auto_tandem = (d_optimal_single < D_MIN)`.
  - Autodetección transición: `auto_tandem = (phi_start > lm_max_avail)`.
  - En tándem: flujo por luminaria = `phi_needed(d, L) / 2`, potencia y flujo de
    zona ×2, `L_est` con flujo doble.
  - Genera **setpoints con posiciones físicas reales A/B** (campos `tandem` y `pair`).
    Esto hace que `photometric_verify.py` coloque las luminarias correctas SIN
    tocar ese módulo.
- Loop de diseño lee `tandem_overrides.get(z_name)` → pasa a `tandem_override`.

**`app.py`**: extrae `tandem_overrides` (§1).

**UI `tunnel.html`**:
- Estado `tandemOverrides` + en payload API `tandem_overrides: tandemOverrides`.
- Tabla de zonas: columna **Tándem** con botón toggle:
  - `⊕ 2× ●` azul `#dbeafe` = auto-detectado
  - `⊕ 2× ✎` violeta `#ede9fe` = forzado manual
  - `1×` gris = individual
  - Click alterna; si coincide con auto, borra el override (vuelve a auto).
- Lista de luminarias: columna **Par** (A/B/—), filas tándem fondo `#f5f0ff`,
  icono `⊕` en ID.

> ⚠️ **PENDIENTE DE VERIFICACIÓN**: probar con un caso real donde CTH·B necesite
> tándem (L_req=312 no alcanzable individual). Confirmar que:
> 1. Se autodetecta y muestra `⊕ 2×` azul.
> 2. La lista muestra pares A/B con offset correcto.
> 3. CIE 140 (photometric_verify) da L_avg coherente con el doble de luminarias.
> 4. El toggle manual ON/OFF funciona y re-dispara el cálculo.

---

## 4. VALORES DE REFERENCIA

### Reflectancias típicas (ρ = reflectancia)
| Superficie | Limpio | Explotación | Muy sucio |
|-----------|--------|-------------|-----------|
| Paredes hormigón | 0.50–0.65 | 0.20–0.40 | 0.10–0.20 |
| Techo hormigón | 0.25–0.45 | 0.05–0.20 | 0.03–0.10 |
| Pavimento asfalto oscuro | 0.07 | — | — |
| Pavimento hormigón | 0.28 | — | — |

Defaults en UI: ρ paredes = 0.40, ρ techo = 0.25.

### Catálogo APHEX (lm / W por punto de operación, en `luminaires.py`)
| Modelo | PCB | 350 mA | 500 mA | 750 mA (4000K) |
|--------|-----|--------|--------|-----------------|
| S | 50G | 97W / 20186lm | 143W / 27769lm | 223W / 39061lm |
| M | 100G | 194W / 40372lm | 286W / 55539lm | 446W / 78123lm |
| L | 150G | 292W / 60559lm | 429W / 83309lm | 670W / 117184lm |

`_BODY_LEN` (largo cuerpo, m): S=0.50, M=0.70, L=1.00.

### Ópticas (por relación w/h)
- F151: w/h < 0.8
- F2M2: 0.8 ≤ w/h < 1.6
- F2MD: w/h ≥ 1.6

### Constantes clave
- `D_MIN = 2.5` m (espaciado mínimo práctico, en `_design_zone_aphex`).
- `_UNIT_FLUX = 10000.0` lm (referencia optimizador).
- Observador CIE 140: `d_observer_m = 60.0` m.
- Grid CIE 140: 10×5 = 50 puntos en celda central.

---

## 5. TRABAJO PENDIENTE / IDEAS

### 5.1 Verificaciones inmediatas (tras reiniciar servidor)
- [ ] **Optimizador**: CTH ya no sobreiluminado (L_req=198 con d>D_MIN).
- [ ] **Lth_b**: CTR2·B usa la curva correcta (portal B, 312) no la de A (198).
- [ ] **Tándem**: caso donde CTH·B lo necesite → autodetección + lista A/B + CIE 140.
- [ ] **GPS**: columnas Lat/Lon aparecen al fijar portal en mapa.
- [ ] **Overlay**: curva verde CIE 140 sobre la azul CIE 88.
- [ ] **ROI**: panel visible sólo en modo radiosidad, KPIs coherentes.
- [ ] **Parada**: card en fase Tráfico calcula d/t con pendiente.

### 5.2 Radiosidad como RE-DISEÑO (no sólo verificación) — DECISIÓN ABIERTA
Actualmente la radiosidad corre DESPUÉS del diseño directo: mantiene las
potencias y añade el aporte indirecto. El usuario preguntó si debería existir un
modo que **recalcule las potencias** aprovechando la luz indirecta (diseñar CON
radiosidad, reduciendo potencia instalada).

- **Estado**: explicado pero NO implementado. Se dejó como está (radiosidad =
  verificación de calidad) y el panel ROI (§3.6) cubre parcialmente la necesidad
  mostrando el ahorro teórico.
- **Si se implementa**: habría que meter el cálculo de radiosidad DENTRO del
  loop del optimizador (diseñar → radiosidad → reducir potencia → verificar).
  Computacionalmente caro. Riesgo: sin cálculo directo previo no hay
  configuración de partida.

### 5.3 Radiosidad sin cálculo directo previo — GUARD PENDIENTE
El usuario preguntó qué pasa si se selecciona radiosidad sin haber hecho antes
el cálculo directo. **Falta añadir validación/guard en la UI** para evitar
estado inconsistente.

### 5.4 Persistencia estado OSM (bug conocido heredado)
El túnel importado de OpenStreetMap no persiste al navegar entre fases (estado
local de `MapSelector`). Ver `CLAUDE.md`.

### 5.5 Capacidad CTH·B con Aphex L
Con Aphex L a 500 mA y D_MIN, sin tándem no se alcanzaba 312 cd/m². El tándem
(§3.8) debería resolverlo. Verificar; si aún falla, considerar:
- Permitir I_max_mA = 750 en zonas críticas.
- Distinto arrangement (bilateral vs central).

### 5.6 Informe Word / Excel — reflejar tándem
Revisar `report.py` y `excel_export.py`: deben mostrar `n_tandem` y las
posiciones A/B en la relación de luminarias exportada. **Probablemente aún no
lo contemplan** (feature tándem es posterior).

---

## 6. GIT / BACKUPS

- Git en OneDrive da error de `index.lock` → usar ZIP para backups.
- Último backup: `BACKUP_20260716_0836.zip`.
- **Al pasar a Claude Code**: si el repo local NO está en OneDrive, git funcionará
  con normalidad. Recomendado: `git init` (si no existe) y commit del estado
  actual antes de seguir.

---

## 7. NOTAS DE DEPURACIÓN (errores encontrados y evitar repetir)

- **Ternarios anidados dentro de strings JS**: causaron un bug donde el texto
  del `sub` de un KPI ROI quedó con comillas mal escapadas. Escribir ternarios
  anidados con cuidado, sin comillas internas conflictivas.
- **SVG arc sweep-flag**: `sweep=0` dibuja CCW (cuenco), `sweep=1` CW (cúpula).
  La sección circular usa `sweep=1`.
- **Carácter `±` en heredoc Python**: dio `SyntaxError`. Usar ASCII "+/-".
- **`n_periods` vs `n_side`**: el optimizador debe usar exactamente la misma
  convención de array que `photometric_verify` (11 grupos) o las estimaciones
  divergen.

---

## 8. CHECKLIST DE ARRANQUE EN CLAUDE CODE

1. Abrir el proyecto en Claude Code (CLI).
2. Leer `CLAUDE.md` (arquitectura base) + este `TRASPASO_A_CODE.md`.
3. `git init` + commit inicial si no hay repo (fuera de OneDrive git funciona).
4. Arrancar servidor: `arrancar_tunnel.bat`.
5. Ejecutar las verificaciones de §5.1 una a una.
6. Decidir §5.2 (radiosidad re-diseño) con el usuario.
7. Continuar con §5.3–5.6.
