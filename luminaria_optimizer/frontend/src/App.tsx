import { ChangeEvent, FormEvent, PointerEvent, useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

const API_URL = (import.meta.env.VITE_OPTIMIZER_API_URL || 'http://127.0.0.1:8760').replace(/\/$/, '');
const GROUP_ANGLES = [11.25, 33.75, 56.25, 78.75, 101.25, 123.75, 146.25, 168.75];
const GROUP_C_ROTATION_DEG = 90;
const CCT_OPTIONS = [2200, 2700, 3000, 3500, 4000, 5000, 5700, 6500];
const MAX_PREVIEW_RAYS = 20000;

type FilePayload = { name: string; base64: string } | null;
const DEFAULT_RAYSET_NAME = 'LUXEON HL2Z_5000000Rays_IESTM25.tm25ray';
type OperatingGroup = { current_ma: number; group_flux_lm: number; vf_v: number; group_power_w: number; tj_c: number; kt: number };
type OperatingPoint = { groups: OperatingGroup[]; total_flux_lm: number; total_driver_power_w: number; solder_temperature_c: number; converged: boolean; power_limit_ok: boolean };
type Metrics = { lavg_cd_m2: number; uo: number; ul: number; ti_pct: number; rei: number; compliant: boolean; criteria: Record<string, boolean>; warnings: string[]; power_limit_ok: boolean };
type GroupPhotometricProfile = { azimuth_deg: number; flux_lm: number; normalized: number[]; max_intensity_cd: number };
type PhotometricProfile = { gamma_deg: number; c_angles_deg: number[]; normalized: number[]; max_intensity_cd: number; group_angles_deg: number[]; groups: GroupPhotometricProfile[] };
type LaneVisualGrid = { lane_index: number; observer_y_m: number; luminance_cd_m2: number[][] };
type LaneProfile = { lane_index: number; observer_y_m: number; luminance_cd_m2: number[] };
type VisualGrid = { xs_m: number[]; ys_m: number[]; illuminance_lx: number[][]; luminance_cd_m2: number[][]; lane_grids?: LaneVisualGrid[]; lane_profiles?: LaneProfile[]; normative_profile?: LaneProfile; worst_lane_index?: number; lane_centres_m?: number[]; lane_widths_m?: number[]; observer_x_m?: number; observer_distance_m?: number };
type ReferenceRoad = { metrics: Metrics; visual_grid?: VisualGrid };
type MapMetric = 'luminance' | 'illuminance' | 'reference-luminance' | 'reference-illuminance';
type OptimizationMode = 'independent' | 'symmetric';
type LdtPair = { c_deg: number; mirror_c_deg: number; max_difference_pct: number; worst_gamma_deg: number; symmetric: boolean };
type LdtDiagnostic = { name: string; company: string; flux_lm: number; power_w: number; c_angles_deg: number[]; gamma_angles_deg: number[]; intensities_cd_per_klm: number[][]; max_intensity_cd_per_klm: number; peak_c_deg?: number; peak_gamma_deg?: number; symmetry_tolerance_pct: number; pairs: LdtPair[]; symmetric: boolean };
type PreviewRayStatus = 'transmitted' | 'missed' | 'untransmitted';
type LedSelection = 'all' | 0 | 1 | 2;
type PreviewRay = { led_index: number; status: PreviewRayStatus; origin_xyz: number[]; entry_xyz: number[] | null; exit_xyz: number[] | null; direction_xyz: number[] | null; power_lm: number; transmitted_power_lm: number; c_deg: number | null; gamma_deg: number | null; tir: boolean; tir_count: number; reflection_points_xyz: number[][]; reflection_surface_indices: number[]; entry_surface_index: number | null; exit_surface_index: number | null };
type GeometryMeshPart = { vertices: number[][]; faces: number[][]; surface_ids?: number[]; surface_labels?: string[] };
type GeometryMesh = { units: string; coordinate_system: string; coordinate_frame: string; lens: GeometryMeshPart; leds: Array<GeometryMeshPart & { led_index: number }> };
type RayAngleConfig = { c_mirror: boolean; c_offset_deg: number; gamma_flip: boolean; c_convention: string; gamma_convention: string };
type GeometryTraceData = { geometry: { solid_count: number; led_count: number; lens_volume: number; lens_faces: number; lens_triangles?: number; lens_bbox_mm: { xmin: number; xmax: number; ymin: number; ymax: number; zmin: number; zmax: number }; led_origins_mm: number[][] }; trace: { source_ray_count: number; led_count: number; traced_ray_count: number; input_flux_lm: number; missed_ray_count: number; missed_flux_lm: number; intercepted_ray_count: number; intercepted_flux_lm: number; transmitted_ray_count: number; transmitted_flux_lm: number; total_internal_reflection_count: number; untransmitted_flux_lm: number; transmission_pct: number; preview_ray_count?: number; preview_status_counts?: Record<string, number> }; ldt: LdtDiagnostic; ldt_base64: string; preview_rays: number[][]; preview_rays_detail?: PreviewRay[]; preview_geometry_mesh?: GeometryMesh; ray_angle_config?: RayAngleConfig };
type Result = { feasible?: boolean; currents_ma: number[]; tilt_deg?: number; operating_point: OperatingPoint; metrics?: Metrics; reference_road?: ReferenceRoad | null; photometric_profile?: PhotometricProfile; visual_grid?: VisualGrid; group_ldt?: LdtDiagnostic; luminaire_ldt?: LdtDiagnostic; reference_luminaire_ldt?: LdtDiagnostic | null; message?: string };

const encodeFile = (file: File): Promise<FilePayload> => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve({ name: file.name, base64: String(reader.result).split(',')[1] || '' });
  reader.onerror = () => reject(reader.error || new Error(`No se pudo leer ${file.name}`));
  reader.readAsDataURL(file);
});

function NumberField({ label, value, onChange, suffix, min, max, step }: { label: string; value: number; onChange: (value: number) => void; suffix?: string; min?: number; max?: number; step?: number }) {
  return <label className="field"><span>{label}</span><div className="number-input"><input type="number" value={value} min={min} max={max} step={step} onChange={event => onChange(Number(event.target.value))} /><small>{suffix}</small></div></label>;
}

function FileDrop({ label, hint, file, accept, onFile, defaultName }: { label: string; hint: string; file: FilePayload; accept: string; onFile: (file: FilePayload) => void; defaultName?: string }) {
  const handle = async (event: ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0];
    if (selected) onFile(await encodeFile(selected));
  };
  return <label className={`file-drop ${file || defaultName ? 'loaded' : ''}`}>
    <input type="file" accept={accept} onChange={handle} />
    <span className="file-glyph">{file ? '✓' : defaultName ? '·' : '+'}</span>
    <span><strong>{file ? file.name : defaultName || label}</strong><small>{file ? 'Archivo cargado' : defaultName ? 'Fuente por defecto · pulsa para cambiar' : hint}</small></span>
  </label>;
}

function App() {
  const [ldt, setLdt] = useState<FilePayload>(null);
  const [modelMode, setModelMode] = useState<'ldt' | 'geometry'>('ldt');
  const [stepFile, setStepFile] = useState<FilePayload>(null);
  const [raysetFile, setRaysetFile] = useState<FilePayload>(null);
  const [rayCount, setRayCount] = useState(10000);
  const [lensIndex, setLensIndex] = useState(1.49);
  const [geometryTrace, setGeometryTrace] = useState<GeometryTraceData | null>(null);
  const [referenceLdt, setReferenceLdt] = useState<FilePayload>(null);
  const [rtable, setRtable] = useState<FilePayload>(null);
  const [currents, setCurrents] = useState<number[]>(Array(8).fill(700));
  const [cct, setCct] = useState(4000);
  const [cri, setCri] = useState(70);
  const [lightingClass, setLightingClass] = useState('M3');
  const [rtableName, setRtableName] = useState('C2');
  const [height, setHeight] = useState(1.0);
  const [spacing, setSpacing] = useState(10.0);
  const [width, setWidth] = useState(3.5);
  const [edgeOffset, setEdgeOffset] = useState(0.5);
  const [tilt, setTilt] = useState(0.0);
  const [lanes, setLanes] = useState(1);
  const [arrangement, setArrangement] = useState('unilateral');
  const [optimizationMode, setOptimizationMode] = useState<OptimizationMode>('independent');
  const [ambient, setAmbient] = useState(25);
  const [tsCoefficient, setTsCoefficient] = useState(0.3);
  const [driverEfficiency, setDriverEfficiency] = useState(0.9);
  const [maintenance, setMaintenance] = useState(0.85);
  const [displayGamma, setDisplayGamma] = useState(45);
  const [selectedLane, setSelectedLane] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [activePanel, setActivePanel] = useState<'model' | 'road' | 'groups'>('model');
  const [groupLdtDiagnostic, setGroupLdtDiagnostic] = useState<LdtDiagnostic | null>(null);
  const [referenceLdtDiagnostic, setReferenceLdtDiagnostic] = useState<LdtDiagnostic | null>(null);

  const laneWidths = useMemo(() => Array(lanes).fill(width), [lanes, width]);
  const totalFlux = result?.operating_point.total_flux_lm;
  const totalPower = result?.operating_point.total_driver_power_w;
  const groupFluxes = result?.operating_point.groups.map(group => group.group_flux_lm) ?? [];
  const maxGroupFlux = Math.max(...groupFluxes, 1);

  const updateCurrent = (index: number, value: number) => setCurrents(previous => previous.map((current, item) => item === index ? value : current));
  const handleLdt = async (file: FilePayload) => {
    setLdt(file);
    setGroupLdtDiagnostic(null);
    if (!file) return;
    try {
      const response = await fetch(`${API_URL}/api/ldt/inspect`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ group_ldt_base64: file.base64 }) });
      if (response.ok) setGroupLdtDiagnostic(await response.json());
    } catch { /* The full calculation will report the error if inspection is unavailable. */ }
  };
  const handleReferenceLdt = async (file: FilePayload) => {
    setReferenceLdt(file);
    setReferenceLdtDiagnostic(null);
    if (!file) return;
    try {
      const response = await fetch(`${API_URL}/api/ldt/inspect`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ group_ldt_base64: file.base64 }) });
      if (response.ok) setReferenceLdtDiagnostic(await response.json());
    } catch { /* The full calculation will report the error if inspection is unavailable. */ }
  };
  const runGeometryTrace = async () => {
    if (!stepFile) {
      setError('Carga el STEP de la lente antes de calcular.');
      return;
    }
    setError(''); setBusy(true);
    try {
      const response = await fetch(`${API_URL}/api/geometry/trace`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          step_base64: stepFile.base64,
          rayset_base64: raysetFile?.base64 || null,
          step_filename: stepFile.name,
          rayset_filename: raysetFile?.name || DEFAULT_RAYSET_NAME,
          sample_count: rayCount,
          chunk_size: 10000,
          lens_index: lensIndex,
          preview_ray_count: MAX_PREVIEW_RAYS,
          c_mirror: true,
          c_offset_deg: 0,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'El trazado geométrico ha fallado.');
      if (!data.preview_geometry_mesh || !Array.isArray(data.preview_rays_detail)) throw new Error('El backend está desactualizado. Cierra y vuelve a arrancar luminaria_optimizer.');
      setGeometryTrace(data);
      setLdt({ name: `LDT generado · ${rayCount.toLocaleString('es-ES')} rayos`, base64: data.ldt_base64 });
      setGroupLdtDiagnostic(data.ldt);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'No se pudo calcular la lente.');
    } finally { setBusy(false); }
  };
  const requestBody = () => {
    if (!ldt || !rtable) throw new Error('Carga el LDT del grupo y una tabla R/C2 antes de calcular.');
    return {
      group_ldt_base64: ldt.base64,
      reference_luminaire_ldt_base64: referenceLdt?.base64 || null,
      rtable_base64: rtable.base64,
      rtable_name: rtableName,
      reference_group_flux_lm: 897.81,
      reference_cct_k: 4000,
      reference_cri: 70,
      cct_k: cct,
      cri,
      currents_ma: currents,
      ambient_temperature_c: ambient,
      ts_coefficient_c_per_w: tsCoefficient,
      driver_efficiency: driverEfficiency,
      multiplexing_mode: 'simultaneous',
      display_gamma_deg: displayGamma,
      height_m: height,
      spacing_m: spacing,
      edge_offset_m: edgeOffset,
      tilt_deg: tilt,
      carriageway_width_m: width * lanes,
      lane_widths_m: laneWidths,
      arrangement,
      optimization_mode: optimizationMode,
      photometry_symmetry: 'asymmetric',
      maintenance_factor: maintenance,
      lighting_class: lightingClass,
    };
  };

  const run = async (endpoint: string, event?: FormEvent) => {
    event?.preventDefault();
    setError(''); setBusy(true);
    try {
      const response = await fetch(`${API_URL}${endpoint}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(requestBody()) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'El backend ha rechazado la solicitud.');
      setResult(data);
      if (data.currents_ma) setCurrents(data.currents_ma);
      if (typeof data.tilt_deg === 'number') setTilt(data.tilt_deg);
      setActivePanel('groups');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'No se pudo completar el cálculo.');
    } finally { setBusy(false); }
  };

  const format = (value: number | undefined, digits = 1) => value == null || Number.isNaN(value) ? '—' : value.toFixed(digits);
  const polarProfile = result?.photometric_profile;
  const polarCurve = polarProfile ? polarProfile.normalized.map((radius, index) => {
    const angle = (polarProfile.c_angles_deg[index] - 90) * Math.PI / 180;
    return `${120 + Math.cos(angle) * radius * 100},${120 + Math.sin(angle) * radius * 100}`;
  }).join(' ') : '';
  const groupPolarCurves = polarProfile?.groups.map(group => group.normalized.map((radius, index) => {
    const angle = (polarProfile.c_angles_deg[index] - 90) * Math.PI / 180;
    return `${120 + Math.cos(angle) * radius * 100},${120 + Math.sin(angle) * radius * 100}`;
  }).join(' ')) ?? [];

  return <main className="app-shell">
    <header className="topbar">
      <div className="brand"><span className="brand-mark">S</span><span><strong>SALVI</strong><small>LUMINAIRE OPTIMIZER</small></span></div>
      <div className="topbar-meta"><span className="status-dot" /> MODELO HL2X / 8 CANALES <i>v0.1</i></div>
    </header>
    <div className="page-grid">
      <section className="hero">
        <p className="eyebrow">OPTICAL CONTROL SYSTEM / 01</p>
        <h1>Diseña la luminaria<br /><em>desde la calzada.</em></h1>
        <p className="hero-copy">Optimización fotométrica de ocho grupos HL2X con corriente independiente, para geometrías viarias de baja altura.</p>
        <div className="hero-stats"><div><strong>8</strong><span>grupos ópticos</span></div><div><strong>50</strong><span>mA por paso</span></div><div><strong>2.0</strong><span>A máximo</span></div></div>
      </section>
      <form className="workspace" onSubmit={event => run('/api/road/calculate', event)}>
        <nav className="panel-tabs" aria-label="Configuración">
          <button type="button" className={activePanel === 'model' ? 'active' : ''} onClick={() => setActivePanel('model')}><b>01</b> Modelo</button>
          <button type="button" className={activePanel === 'road' ? 'active' : ''} onClick={() => setActivePanel('road')}><b>02</b> Calzada</button>
          <button type="button" className={activePanel === 'groups' ? 'active' : ''} onClick={() => setActivePanel('groups')}><b>03</b> Corrientes</button>
        </nav>
        {activePanel === 'model' && <section className="panel-content">
            <div className="section-heading"><div><p className="eyebrow">BASE FOTOMÉTRICA</p><h2>Modelo de referencia</h2></div><span className="tag">HL2X / 3535</span></div>
           <div className="model-mode" role="group" aria-label="Modo de entrada del modelo"><button type="button" className={modelMode === 'ldt' ? 'active' : ''} onClick={() => setModelMode('ldt')}>Usar LDT</button><button type="button" className={modelMode === 'geometry' ? 'active' : ''} onClick={() => setModelMode('geometry')}>Calcular desde STEP</button></div>
           {modelMode === 'ldt' ? <div className="file-grid"><FileDrop label="LDT del grupo" hint="3 LED + lente / EULUMDAT" file={ldt} accept=".ldt" onFile={handleLdt} /><FileDrop label="LDT completo de referencia" hint="Luminaria completa / DIALux" file={referenceLdt} accept=".ldt" onFile={handleReferenceLdt} /></div> : <>
              <div className="file-grid"><FileDrop label="STEP: lente + 3 LED" hint="ensamblaje CAD / mm" file={stepFile} accept=".step,.stp" onFile={setStepFile} /><FileDrop label="Ray file TM-25" hint="fuente LED / .tm25ray" file={raysetFile} defaultName={DEFAULT_RAYSET_NAME} accept=".tm25ray,.tm25,.ray" onFile={setRaysetFile} /></div>
               <div className="geometry-controls"><label className="field"><span>Rayos calculados por LED</span><select value={rayCount} onChange={event => setRayCount(Number(event.target.value))}><option value={10000}>10.000 · rápido</option><option value={100000}>100.000 · validación</option><option value={1000000}>1.000.000 · LDT final</option><option value={5000000}>5.000.000 · máxima precisión</option></select></label><NumberField label="Índice de refracción" value={lensIndex} onChange={setLensIndex} suffix="n" step={0.001} min={1.0} max={3.0} /><div><p className="geometry-note">C mirror · Embree acelerado · visor hasta {MAX_PREVIEW_RAYS.toLocaleString('es-ES')}</p><button type="button" className="geometry-run" onClick={runGeometryTrace} disabled={busy}>{busy ? 'Trazando rayos…' : 'Calcular LDT desde la lente'} <span>→</span></button></div></div>
             {geometryTrace && <GeometryTraceView data={geometryTrace} />}
             {geometryTrace && <LdtDiagnostics title="LDT CALCULADO / 3 LED + LENTE" diagnostic={geometryTrace.ldt} showPlaneProfiles />}
           </>}
           {modelMode === 'ldt' && groupLdtDiagnostic && <LdtDiagnostics title="LDT DEL GRUPO / 3 LED + LENTE" diagnostic={groupLdtDiagnostic} showPlaneProfiles />}
           {referenceLdtDiagnostic && <LdtDiagnostics title="LDT COMPLETO / REFERENCIA DIALUX" diagnostic={referenceLdtDiagnostic} />}
          <div className="field-grid three"><label className="field"><span>CCT</span><select value={cct} onChange={event => setCct(Number(event.target.value))}>{CCT_OPTIONS.map(value => <option key={value} value={value}>{value} K</option>)}</select></label><label className="field"><span>CRI</span><select value={cri} onChange={event => setCri(Number(event.target.value))}><option value={70}>70</option><option value={80}>80</option><option value={90}>90</option></select></label></div>
          <div className="field-grid three"><NumberField label="Ambiente" value={ambient} onChange={setAmbient} suffix="°C" min={-40} max={80} /><NumberField label="Coef. Tsp" value={tsCoefficient} onChange={setTsCoefficient} suffix="°C/W" step={0.01} min={0} /><NumberField label="Driver" value={driverEfficiency} onChange={setDriverEfficiency} suffix="η" step={0.01} min={0.1} max={1} /></div>
          <p className="note"><span>i</span> El flujo del LDT es el anclaje fotométrico del grupo. La temperatura y la corriente modifican el flujo mediante el modelo iterativo HL2X.</p>
        </section>}
        {activePanel === 'road' && <section className="panel-content">
          <div className="section-heading"><div><p className="eyebrow">ESCENARIO VIAL</p><h2>Geometría de cálculo</h2></div><span className="tag">EN 13201 / M</span></div>
          <div className="field-grid three"><NumberField label="Altura fotométrica" value={height} onChange={setHeight} suffix="m" step={0.05} min={0.5} max={5} /><NumberField label="Interdistancia" value={spacing} onChange={setSpacing} suffix="m" step={0.5} min={1} max={40} /><NumberField label="Anchura de carril" value={width} onChange={setWidth} suffix="m" step={0.1} min={2} max={8} /></div>
           <div className="field-grid three"><NumberField label="Offset desde el canto" value={edgeOffset} onChange={setEdgeOffset} suffix="m" step={0.1} min={0} max={5} /><NumberField label="Tilt LDT luminaria" value={tilt} onChange={setTilt} suffix="°" step={0.5} min={-10} max={10} /><div className="mode-field road-mode-field"><span>Distribución de corrientes</span><div className="mode-toggle" role="group" aria-label="Modo de optimización"><button type="button" className={optimizationMode === 'independent' ? 'active' : ''} onClick={() => setOptimizationMode('independent')}>Independiente</button><button type="button" className={optimizationMode === 'symmetric' ? 'active' : ''} onClick={() => setOptimizationMode('symmetric')}>Simétrico</button></div><small>Simétrico impone G1=G8, G2=G7, G3=G6 y G4=G5.</small></div></div>
          <div className="file-grid"><FileDrop label="Tabla de reflexión" hint="R1, R2, R3, R4 o C2" file={rtable} accept=".rtb,.txt" onFile={setRtable} /></div>
          <div className="field-grid three"><label className="field"><span>Tabla activa</span><select value={rtableName} onChange={event => setRtableName(event.target.value)}><option value="C2">C2 rasante</option><option value="R1">R1</option><option value="R2">R2</option><option value="R3">R3</option><option value="R4">R4</option></select></label><label className="field"><span>Carriles</span><select value={lanes} onChange={event => setLanes(Number(event.target.value))}>{[1, 2, 3, 4].map(value => <option key={value} value={value}>{value}</option>)}</select></label><label className="field"><span>Disposición</span><select value={arrangement} onChange={event => setArrangement(event.target.value)}><option value="unilateral">Unilateral</option><option value="bilateral_paired">Bilateral pareada</option><option value="bilateral_staggered">Bilateral tresbolillo</option></select></label></div>
          <div className="field-grid three"><label className="field"><span>Clase luminotécnica</span><select value={lightingClass} onChange={event => setLightingClass(event.target.value)}>{['M1', 'M2', 'M3', 'M4', 'M5', 'M6'].map(value => <option key={value}>{value}</option>)}</select></label></div>
          <RoadAnimation width={width * lanes} height={height} spacing={spacing} edgeOffset={edgeOffset} arrangement={arrangement} />
          <p className="note"><span>i</span> Las luminarias opuestas se giran 180° y utilizan el mismo perfil de ocho corrientes.</p>
        </section>}
         {activePanel === 'groups' && <section className="panel-content">
           <div className="section-heading"><div><p className="eyebrow">PERFIL DE CONTROL</p><h2>Corriente por grupo</h2></div><span className="tag">0 — 2000 mA</span></div>
            <div className="group-list">{GROUP_ANGLES.map((angle, index) => <div className="group-row" key={angle}><div className="group-index">G{String(index + 1).padStart(2, '0')}</div><div className="group-angle"><strong>{angle.toFixed(2)}°</strong><small>azimut C</small></div><input className="range" type="range" min={0} max={2000} step={1} value={currents[index]} onChange={event => updateCurrent(index, Number(event.target.value))} /><input className="current-select" type="number" min={0} max={2000} step={1} value={currents[index]} onChange={event => updateCurrent(index, Number(event.target.value))} /><span className="group-flow">{result ? `${format(result.operating_point.groups[index]?.group_flux_lm, 0)} lm` : '—'}</span></div>)}</div>
          <button className="equalize" type="button" onClick={() => setCurrents(Array(8).fill(currents[0]))}>Igualar los ocho grupos</button>
        </section>}
        {error && <div className="error-banner" role="alert">{error}</div>}
        <div className="action-bar"><button className="secondary-button" type="button" onClick={() => run('/api/road/calculate')} disabled={busy}>{busy ? 'Calculando…' : 'Evaluar perfil'}</button><button className="primary-button" type="button" onClick={() => run('/api/optimize')} disabled={busy}>{busy ? 'Optimizando…' : 'Optimizar corrientes'} <span>→</span></button></div>
      </form>
    </div>
    <section className="results-section"><div className="results-heading"><div><p className="eyebrow">LIVE OUTPUT / {lightingClass}</p><h2>Lectura de la solución</h2></div><span className={`result-state ${result?.metrics?.compliant ? 'good' : result ? 'warn' : ''}`}>{result?.metrics?.compliant ? 'CONFORME' : result ? 'REVISAR' : 'SIN CÁLCULO'}</span></div>
       <div className="metric-grid"><Metric label="Flujo total" value={totalFlux ? `${format(totalFlux, 0)} lm` : '—'} /><Metric label="Potencia entrada" value={totalPower ? `${format(totalPower, 1)} W` : '—'} /><Metric label="Lavg" value={result?.metrics ? `${format(result.metrics.lavg_cd_m2, 2)} cd/m²` : '—'} /><Metric label="Uo" value={result?.metrics ? format(result.metrics.uo, 2) : '—'} /><Metric label="Ul" value={result?.metrics ? format(result.metrics.ul, 2) : '—'} /></div>
       {result?.reference_road && result.metrics && <ReferenceComparison calculated={result.metrics} reference={result.reference_road.metrics} />}
         <div className="visual-card"><div className="card-title"><span>MAPA PUNTO A PUNTO</span><small>isocurvas / luminancia cd/m²</small></div>{result?.visual_grid ? <LuminanceMap grid={result.visual_grid} referenceGrid={result.reference_road?.visual_grid} groupLdt={result.group_ldt} luminaireLdt={result.luminaire_ldt} referenceLdt={result.reference_luminaire_ldt || undefined} luminaireHeight={height} carriagewayWidth={width * lanes} spacing={spacing} edgeOffset={edgeOffset} arrangement={arrangement} selectedLane={selectedLane} onLaneChange={setSelectedLane} /> : <div className="empty-result">Ejecuta una evaluación para visualizar la distribución sobre la calzada.</div>}</div>
        {result?.visual_grid?.normative_profile && <NormativeGraph xs={result.visual_grid.xs_m} profiles={result.visual_grid.lane_profiles || []} worstLane={result.visual_grid.worst_lane_index ?? result.visual_grid.normative_profile.lane_index} selectedLane={selectedLane} onLaneChange={setSelectedLane} />}
         {result?.group_ldt && <LdtDiagnostics title="DIAGNÓSTICO FOTOMÉTRICO / GRUPO" diagnostic={result.group_ldt} showPlaneProfiles />}
        {result?.luminaire_ldt && <LdtDiagnostics title="DIAGNÓSTICO FOTOMÉTRICO / LUMINARIA CALCULADA" diagnostic={result.luminaire_ldt} />}
        {result?.reference_luminaire_ldt && <LdtDiagnostics title="DIAGNÓSTICO FOTOMÉTRICO / REFERENCIA DIALUX" diagnostic={result.reference_luminaire_ldt} />}
      <div className="group-results"><div className="card-title"><span>RESULTADO POR GRUPO</span><small>perfil aplicado en todas las luminarias</small></div><div className="group-results-grid">{GROUP_ANGLES.map((angle, index) => { const group = result?.operating_point.groups[index]; return <div className="group-result" key={angle}><strong>G{index + 1}</strong><span>{angle.toFixed(2)}° C</span><b>{result ? `${format(result.currents_ma[index], 0)} mA` : '—'}</b><small>{group ? `${format(group.group_flux_lm, 0)} lm · ${format(group.group_power_w, 1)} W` : 'sin cálculo'}</small></div>; })}</div></div>
       <div className="result-lower"><div className="profile-card"><div className="card-title"><span>PERFIL AZIMUTAL ACTIVO</span><label className="gamma-picker">gamma <select value={displayGamma} onChange={event => setDisplayGamma(Number(event.target.value))}><option value={0}>0°</option><option value={15}>15°</option><option value={30}>30°</option><option value={45}>45°</option><option value={60}>60°</option><option value={75}>75°</option><option value={90}>90°</option></select></label></div><div className="polar"><div className="polar-ring ring-1" /><div className="polar-ring ring-2" /><div className="polar-axis axis-x" /><div className="polar-axis axis-y" />{groupPolarCurves.map((points, index) => <svg className="polar-curve group-curve" viewBox="0 0 240 240" key={`group-curve-${index}`}><polyline points={points} /></svg>)}{polarCurve && <svg className="polar-curve total-curve" viewBox="0 0 240 240" aria-label={`Fotometría a gamma ${displayGamma} grados`}><polyline points={polarCurve} /></svg>}{GROUP_ANGLES.map((angle, index) => <span key={angle} className="polar-ray" style={{ transform: `rotate(${angle - 90}deg)`, height: result ? `${groupFluxes[index] / maxGroupFlux * 72}%` : '0%' }}><i /></span>)}<div className="polar-center">8<span>G</span></div></div><div className="polar-legend"><span className="photometry-key">curva gruesa: suma</span><span>curvas finas: grupos relativos</span></div>{polarProfile && <p className="profile-readout">Imax {format(polarProfile.max_intensity_cd, 0)} cd · gamma {polarProfile.gamma_deg.toFixed(0)}° · máximos orientados por grupo</p>}</div><div className="criteria-card"><div className="card-title"><span>CRITERIOS EN 13201</span><small>{rtableName} / {cct} K / CRI {cri}</small></div>{result?.metrics ? Object.entries(result.metrics.criteria).map(([name, passed]) => <div className="criterion" key={name}><span>{name}</span><strong className={passed ? 'pass' : 'fail'}>{passed ? 'OK' : 'NO'}</strong></div>) : <div className="empty-result">Ejecuta una evaluación para ver el cumplimiento de la clase {lightingClass}.</div>}{result?.metrics?.warnings.map(warning => <p className="warning" key={warning}>! {warning}</p>)}</div></div>
    </section>
    <footer><span>SALVI LIGHTING / ENGINEERING TOOLS</span><span>HL2X 3535 · PROFILE 8×3 SERIES · {API_URL}</span></footer>
  </main>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div>; }

const RAY_STATUS_LABELS: Record<PreviewRayStatus, string> = { transmitted: 'Transmitido', missed: 'No interceptado', untransmitted: 'No transmitido' };
const RAY_STATUS_COLORS: Record<PreviewRayStatus, string> = { transmitted: '#b9e77a', missed: '#879a91', untransmitted: '#ef7348' };
const LED_COLORS = ['#68d8ff', '#f4c95d', '#d995ff'];

function disposeThreeObject(object: THREE.Object3D) {
  object.traverse(child => {
    if (child instanceof THREE.Mesh || child instanceof THREE.LineSegments || child instanceof THREE.Line) child.geometry.dispose();
    if (child instanceof THREE.Mesh || child instanceof THREE.LineSegments || child instanceof THREE.Line) {
      const materials = Array.isArray(child.material) ? child.material : [child.material];
      materials.forEach(material => material.dispose());
    }
  });
}

function makeGeometryMesh(part: GeometryMeshPart, material: THREE.Material) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(part.vertices.flat(), 3));
  geometry.setIndex(part.faces.flat());
  geometry.computeVertexNormals();
  return new THREE.Mesh(geometry, material);
}

function GeometryAnglePanel({ data, ray, rayIndex }: { data: GeometryTraceData; ray: PreviewRay | null; rayIndex: number | null }) {
  const c = ray?.c_deg ?? data.ldt.peak_c_deg ?? null;
  const gamma = ray?.gamma_deg ?? data.ldt.peak_gamma_deg ?? null;
  const angle = ((c ?? 0) - 90) * Math.PI / 180;
  const radius = Math.min(73, Math.max(0, (gamma ?? 0) / 180) * 73);
  const point = { x: 90 + Math.cos(angle) * radius, y: 90 + Math.sin(angle) * radius };
  const config = data.ray_angle_config;
  return <aside className="geometry-angle-panel">
    <div className="geometry-side-title"><span>ÁNGULO FOTOMÉTRICO</span><small>{ray ? `RAYO ${rayIndex == null ? '' : rayIndex + 1}` : 'PICO LDT'}</small></div>
    <svg className="geometry-angle-map" viewBox="0 0 180 180" role="img" aria-label="Mapa polar de C y gamma">
      <circle cx="90" cy="90" r="73" fill="#173e36" stroke="#41685b" /><circle cx="90" cy="90" r="48" fill="none" stroke="#41685b" /><circle cx="90" cy="90" r="24" fill="none" stroke="#41685b" /><path d="M17 90H163M90 17V163" stroke="#41685b" strokeDasharray="2 3" /><line x1="90" y1="90" x2={point.x} y2={point.y} stroke="#b9e77a" strokeWidth="1.2" /><circle cx={point.x} cy={point.y} r="4" fill="#ef7348" stroke="#f7f8f3" strokeWidth="1" /><text x="90" y="12" textAnchor="middle" fill="#b9e77a" fontSize="8" fontFamily="DM Mono, monospace">C0 / gamma 0</text><text x="169" y="93" textAnchor="end" fill="#b9e77a" fontSize="8" fontFamily="DM Mono, monospace">C90</text><text x="90" y="176" textAnchor="middle" fill="#b9e77a" fontSize="8" fontFamily="DM Mono, monospace">C180</text><text x="12" y="93" fill="#b9e77a" fontSize="8" fontFamily="DM Mono, monospace">C270</text>
    </svg>
    <div className="geometry-angle-readout"><strong>{c == null ? '—' : `${c.toFixed(1)}°`} <small>C</small></strong><strong>{gamma == null ? '—' : `${gamma.toFixed(1)}°`} <small>gamma</small></strong></div>
    <p className="geometry-angle-note">Radio = gamma / 180° · color de selección = naranja</p>
    {ray && <div className="geometry-ray-readout"><span><i style={{ background: RAY_STATUS_COLORS[ray.status] }} />{RAY_STATUS_LABELS[ray.status]}</span><span>LED {ray.led_index + 1} · {ray.transmitted_power_lm.toExponential(2)} lm</span>{ray.tir && <span className="geometry-tir">TIR × {ray.tir_count}</span>}</div>}
    {config && <p className="geometry-angle-config">{config.c_mirror ? 'C espejo' : 'C directo'} · offset {config.c_offset_deg.toFixed(1)}°</p>}
  </aside>;
}

function GeometryTraceView({ data }: { data: GeometryTraceData }) {
  const details = data.preview_rays_detail ?? [];
  const [rayLimit, setRayLimit] = useState(Math.min(5000, details.length || 5000));
  const [colorMode, setColorMode] = useState<'status' | 'led'>('status');
  const [ledSelection, setLedSelection] = useState<LedSelection>('all');
  const [selectedSurfaceIndex, setSelectedSurfaceIndex] = useState<number | null>(null);
  const [statusVisibility, setStatusVisibility] = useState<Record<PreviewRayStatus, boolean>>({ transmitted: true, missed: true, untransmitted: true });
  const [showRays, setShowRays] = useState(true);
  const [showLens, setShowLens] = useState(true);
  const [showLeds, setShowLeds] = useState(true);
  const [showGrid, setShowGrid] = useState(true);
  const [showAxes, setShowAxes] = useState(true);
  const [selectedRayIndex, setSelectedRayIndex] = useState<number | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const viewerSectionRef = useRef<HTMLElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const lensMeshRef = useRef<THREE.Mesh | null>(null);
  const lensGroupRef = useRef<THREE.Group | null>(null);
  const ledGroupRef = useRef<THREE.Group | null>(null);
  const surfaceHighlightRef = useRef<THREE.Group | null>(null);
  const gridRef = useRef<THREE.Object3D | null>(null);
  const axesRef = useRef<THREE.Object3D | null>(null);
  const rayGroupRef = useRef<THREE.Group | null>(null);
  const selectedGroupRef = useRef<THREE.Group | null>(null);
  const selectedRayIndexRef = useRef<number | null>(null);
  const selectedSurfaceIndexRef = useRef<number | null>(null);
  const rebuildRaysRef = useRef<() => void>(() => undefined);
  const rebuildSurfaceRef = useRef<() => void>(() => undefined);
  const rebuildSelectedRef = useRef<() => void>(() => undefined);
  const resetViewRef = useRef<() => void>(() => undefined);
  const settingsRef = useRef({ rayLimit, colorMode, ledSelection, surfaceIndex: selectedSurfaceIndex, statusVisibility, showRays });
  const selectedRay = selectedRayIndex == null ? null : details[selectedRayIndex] || null;
  const maxRayCount = details.length;
  const rayOptions = [...new Set([100, 500, 1000, 2500, 5000, 10000, 20000].filter(value => value < maxRayCount).concat(maxRayCount > 0 ? [maxRayCount] : []))].sort((a, b) => a - b);
  selectedRayIndexRef.current = selectedRayIndex;
  selectedSurfaceIndexRef.current = selectedSurfaceIndex;

  useEffect(() => {
    setRayLimit(Math.min(5000, details.length || 5000));
    setSelectedRayIndex(null);
    setSelectedSurfaceIndex(null);
  }, [data]);

  useEffect(() => {
    const handleFullscreen = () => setIsFullscreen(document.fullscreenElement === viewerSectionRef.current);
    document.addEventListener('fullscreenchange', handleFullscreen);
    return () => document.removeEventListener('fullscreenchange', handleFullscreen);
  }, []);

  useEffect(() => {
    const container = canvasRef.current;
    const meshPayload = data.preview_geometry_mesh;
    if (!container || !meshPayload) return undefined;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#102d28');
    const camera = new THREE.PerspectiveCamera(42, 1, 0.01, 1000);
    camera.up.set(0, 0, 1);
    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.className = 'geometry-canvas-element';
    container.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.screenSpacePanning = true;
    controls.mouseButtons.LEFT = THREE.MOUSE.ROTATE;
    controls.mouseButtons.RIGHT = THREE.MOUSE.PAN;
    controls.touches.ONE = THREE.TOUCH.ROTATE;
    controls.touches.TWO = THREE.TOUCH.DOLLY_PAN;
    scene.add(new THREE.HemisphereLight(0xdcebd7, 0x153b34, 2.2));
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.6);
    keyLight.position.set(25, -35, 45);
    scene.add(keyLight);

    const modelGroup = new THREE.Group();
    const lensGroup = new THREE.Group();
    const ledGroup = new THREE.Group();
    modelGroup.add(lensGroup, ledGroup);
    scene.add(modelGroup);
    const lensMaterial = new THREE.MeshPhysicalMaterial({ color: '#b9e77a', transparent: true, opacity: .34, roughness: .28, metalness: .02, side: THREE.DoubleSide, depthWrite: false });
    const lensMesh = makeGeometryMesh(meshPayload.lens, lensMaterial);
    lensGroup.add(lensMesh);
    lensMesh.userData.surfaceIds = meshPayload.lens.surface_ids || [];
    lensMeshRef.current = lensMesh;
    const lensEdges = new THREE.LineSegments(new THREE.EdgesGeometry(lensMesh.geometry, 24), new THREE.LineBasicMaterial({ color: '#dcebd7', transparent: true, opacity: .34 }));
    lensGroup.add(lensEdges);
    const surfaceHighlight = new THREE.Group();
    scene.add(surfaceHighlight);
    surfaceHighlightRef.current = surfaceHighlight;
    const modelBox = new THREE.Box3().setFromObject(modelGroup);
    const modelSize = modelBox.getSize(new THREE.Vector3());
    const extent = Math.max(modelSize.x, modelSize.y, modelSize.z, 1);
    meshPayload.leds.forEach((led, index) => {
      const material = new THREE.MeshStandardMaterial({ color: LED_COLORS[index % LED_COLORS.length], transparent: true, opacity: .78, roughness: .36, metalness: .1, side: THREE.DoubleSide });
      const mesh = makeGeometryMesh(led, material);
      ledGroup.add(mesh);
      const origin = data.geometry.led_origins_mm[index];
      if (origin) {
        const marker = new THREE.Mesh(new THREE.SphereGeometry(extent * .025, 12, 8), new THREE.MeshBasicMaterial({ color: LED_COLORS[index % LED_COLORS.length] }));
        marker.position.set(origin[0], origin[1], origin[2]);
        ledGroup.add(marker);
      }
    });
    const grid = new THREE.GridHelper(Math.max(50, extent * 4), 24, '#41685b', '#284b43');
    grid.rotation.x = Math.PI / 2;
    scene.add(grid);
    const axes = new THREE.AxesHelper(Math.max(10, extent * .8));
    scene.add(axes);
    const cGuideGeometry = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(-extent * .65, 0, 0), new THREE.Vector3(extent * .65, 0, 0),
      new THREE.Vector3(0, -extent * .65, 0), new THREE.Vector3(0, extent * .65, 0),
    ]);
    scene.add(new THREE.LineSegments(cGuideGeometry, new THREE.LineBasicMaterial({ color: '#5b8975', transparent: true, opacity: .45 })));
    const rayGroup = new THREE.Group();
    const selectedGroup = new THREE.Group();
    scene.add(rayGroup, selectedGroup);
    lensGroupRef.current = lensGroup;
    ledGroupRef.current = ledGroup;
    gridRef.current = grid;
    axesRef.current = axes;
    rayGroupRef.current = rayGroup;
    selectedGroupRef.current = selectedGroup;

    const fitView = () => {
      const bounds = new THREE.Box3().setFromObject(modelGroup);
      const center = bounds.getCenter(new THREE.Vector3());
      const size = bounds.getSize(new THREE.Vector3());
      const radius = Math.max(size.x, size.y, size.z, 1);
      camera.position.copy(center).add(new THREE.Vector3(radius * 1.65, -radius * 1.75, radius * 1.2));
      camera.near = radius / 100;
      camera.far = radius * 30;
      camera.updateProjectionMatrix();
      controls.target.copy(center);
      controls.update();
    };
    resetViewRef.current = fitView;
    fitView();

    const buildLine = (records: Array<{ ray: PreviewRay; index: number }>, highlight = false) => {
      const positions: number[] = [];
      const colors: number[] = [];
      const segmentMap: number[] = [];
      const rayLength = Math.max(extent * .22, 2.5);
      const addSegment = (start: THREE.Vector3, end: THREE.Vector3, color: THREE.Color, index: number) => {
        positions.push(start.x, start.y, start.z, end.x, end.y, end.z);
        colors.push(color.r, color.g, color.b, color.r, color.g, color.b);
        segmentMap.push(index);
      };
      records.forEach(({ ray, index }) => {
        const origin = new THREE.Vector3(...ray.origin_xyz);
        const direction = new THREE.Vector3(...(ray.direction_xyz || [0, 0, 1])).normalize();
        const entry = ray.entry_xyz ? new THREE.Vector3(...ray.entry_xyz) : null;
        const exit = ray.exit_xyz ? new THREE.Vector3(...ray.exit_xyz) : null;
        const reflections = (ray.reflection_points_xyz || []).map(point => new THREE.Vector3(...point));
        const activeColorMode = settingsRef.current.colorMode;
        const base = highlight ? new THREE.Color('#ffffff') : new THREE.Color(activeColorMode === 'led' ? LED_COLORS[ray.led_index % LED_COLORS.length] : (RAY_STATUS_COLORS[ray.status] || '#879a91'));
        const incoming = highlight ? base : new THREE.Color(activeColorMode === 'led' ? LED_COLORS[ray.led_index % LED_COLORS.length] : '#68d8ff');
        const internal = highlight ? base : new THREE.Color(ray.tir && activeColorMode === 'status' ? '#f4c95d' : base);
        if (!entry) {
          addSegment(origin, origin.clone().add(direction.clone().multiplyScalar(rayLength)), base, index);
          return;
        }
        addSegment(origin, entry, incoming, index);
        const insidePoints = [entry, ...reflections];
        if (exit) insidePoints.push(exit);
        for (let pointIndex = 0; pointIndex < insidePoints.length - 1; pointIndex += 1) addSegment(insidePoints[pointIndex], insidePoints[pointIndex + 1], internal, index);
        const finalPoint = insidePoints[insidePoints.length - 1];
        addSegment(finalPoint, finalPoint.clone().add(direction.clone().multiplyScalar(rayLength)), exit ? base : internal, index);
      });
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
      geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
      const material = new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: highlight ? .98 : .72, depthTest: !highlight });
      const line = new THREE.LineSegments(geometry, material);
      line.userData.segmentMap = segmentMap;
      return line;
    };
    const clearGroup = (group: THREE.Group) => {
      while (group.children.length) {
        const child = group.children.pop();
        if (child) disposeThreeObject(child);
      }
    };
    const rebuildSurface = () => {
      clearGroup(surfaceHighlight);
      const surfaceIndex = selectedSurfaceIndexRef.current;
      const surfaceIds = meshPayload.lens.surface_ids || [];
      if (surfaceIndex == null || !surfaceIds.length) return;
      const faces = meshPayload.lens.faces.filter((_, index) => surfaceIds[index] === surfaceIndex);
      if (!faces.length) return;
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(meshPayload.lens.vertices.flat(), 3));
      geometry.setIndex(faces.flat());
      geometry.computeVertexNormals();
      surfaceHighlight.add(new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ color: '#ef7348', transparent: true, opacity: .62, side: THREE.DoubleSide, depthTest: false })));
    };
    const rebuildRays = () => {
      clearGroup(rayGroup);
      if (!settingsRef.current.showRays) return;
      const surfaceIndex = settingsRef.current.surfaceIndex;
      const records = details.map((ray, index) => ({ ray, index })).filter(({ ray }) => (settingsRef.current.ledSelection === 'all' || ray.led_index === settingsRef.current.ledSelection) && (surfaceIndex == null || ray.entry_surface_index === surfaceIndex || ray.exit_surface_index === surfaceIndex || ray.reflection_surface_indices.includes(surfaceIndex)) && settingsRef.current.statusVisibility[ray.status]).slice(0, settingsRef.current.rayLimit);
      if (records.length) rayGroup.add(buildLine(records));
    };
    const rebuildSelected = () => {
      clearGroup(selectedGroup);
      const index = selectedRayIndexRef.current;
      if (index == null || !details[index]) return;
      selectedGroup.add(buildLine([{ ray: details[index], index }], true));
    };
    rebuildRaysRef.current = rebuildRays;
    rebuildSurfaceRef.current = rebuildSurface;
    rebuildSelectedRef.current = rebuildSelected;
    rebuildRays();
    rebuildSurface();
    rebuildSelected();

    const raycaster = new THREE.Raycaster();
    raycaster.params.Line.threshold = Math.max(extent * .012, .18);
    const pointer = new THREE.Vector2();
    const handleClick = (event: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObject(rayGroup, true)[0];
      const surfaceHit = raycaster.intersectObject(lensMesh, false)[0];
      const surfaceIds = lensMesh.userData.surfaceIds as number[] | undefined;
      if ((event.shiftKey || !hit) && surfaceHit?.faceIndex != null && surfaceIds?.[surfaceHit.faceIndex] != null) {
        setSelectedSurfaceIndex(surfaceIds[surfaceHit.faceIndex]);
        setSelectedRayIndex(null);
        return;
      }
      if (!hit || hit.index == null) return;
      const line = hit.object as THREE.LineSegments;
      const segmentMap = line.userData.segmentMap as number[] | undefined;
      const segmentIndex = Math.floor(hit.index / 2);
      const recordIndex = segmentMap?.[segmentIndex];
      if (recordIndex != null) setSelectedRayIndex(recordIndex);
    };
    renderer.domElement.addEventListener('click', handleClick);
    const resize = () => {
      const width = Math.max(container.clientWidth, 260);
      const height = Math.max(container.clientHeight, 360);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();
    let animationFrame = 0;
    const animate = () => {
      controls.update();
      renderer.render(scene, camera);
      animationFrame = window.requestAnimationFrame(animate);
    };
    animate();
    return () => {
      window.cancelAnimationFrame(animationFrame);
      observer.disconnect();
      renderer.domElement.removeEventListener('click', handleClick);
      controls.dispose();
      disposeThreeObject(scene);
      renderer.dispose();
      if (renderer.domElement.parentElement === container) container.removeChild(renderer.domElement);
      lensGroupRef.current = null;
      lensMeshRef.current = null;
      ledGroupRef.current = null;
      surfaceHighlightRef.current = null;
      gridRef.current = null;
      axesRef.current = null;
      rayGroupRef.current = null;
      selectedGroupRef.current = null;
    };
  }, [data]);

  useEffect(() => {
    settingsRef.current = { rayLimit, colorMode, ledSelection, surfaceIndex: selectedSurfaceIndex, statusVisibility, showRays };
    if (lensGroupRef.current) lensGroupRef.current.visible = showLens;
    if (ledGroupRef.current) ledGroupRef.current.visible = showLeds;
    if (gridRef.current) gridRef.current.visible = showGrid;
    if (axesRef.current) axesRef.current.visible = showAxes;
    const surfaceIndex = selectedSurfaceIndex;
    const selectedSurfaceMatches = surfaceIndex == null || Boolean(selectedRay && (selectedRay.entry_surface_index === surfaceIndex || selectedRay.exit_surface_index === surfaceIndex || selectedRay.reflection_surface_indices.includes(surfaceIndex)));
    if (selectedGroupRef.current) selectedGroupRef.current.visible = showRays && Boolean(selectedRay) && (ledSelection === 'all' || selectedRay?.led_index === ledSelection) && selectedSurfaceMatches && Boolean(selectedRay && statusVisibility[selectedRay.status]);
    rebuildRaysRef.current();
    rebuildSurfaceRef.current();
  }, [rayLimit, colorMode, ledSelection, selectedSurfaceIndex, statusVisibility, showRays, showLens, showLeds, showGrid, showAxes, selectedRay]);

  useEffect(() => { rebuildSelectedRef.current(); }, [selectedRayIndex]);

  const toggleStatus = (status: PreviewRayStatus) => setStatusVisibility(previous => ({ ...previous, [status]: !previous[status] }));
  const selectedCount = details.filter(ray => (ledSelection === 'all' || ray.led_index === ledSelection) && (selectedSurfaceIndex == null || ray.entry_surface_index === selectedSurfaceIndex || ray.exit_surface_index === selectedSurfaceIndex || ray.reflection_surface_indices.includes(selectedSurfaceIndex)) && statusVisibility[ray.status]).length;
  const ledCounts = [0, 1, 2].map(index => details.filter(ray => ray.led_index === index).length);
  const surfaceLabels = data.preview_geometry_mesh?.lens.surface_labels ?? [];
  const selectedSurfaceLabel = selectedSurfaceIndex == null ? '' : surfaceLabels[selectedSurfaceIndex] || `Superficie ${selectedSurfaceIndex + 1}`;
  const clearSurfaceFilter = () => { setSelectedSurfaceIndex(null); setSelectedRayIndex(null); };
  const toggleFullscreen = () => {
    if (!viewerSectionRef.current) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void viewerSectionRef.current.requestFullscreen();
  };
  return <section ref={viewerSectionRef} className={`geometry-preview${expanded ? ' geometry-preview-expanded' : ''}`}>
    <div className="geometry-preview-head"><div><span>VISOR 3D / GEOMETRÍA + RAYOS</span><small>{data.trace.traced_ray_count.toLocaleString('es-ES')} trazados · {details.length.toLocaleString('es-ES')} cargados · coordenadas mm{selectedSurfaceLabel ? ` · filtro: ${selectedSurfaceLabel}` : ''}</small></div><div className="geometry-head-actions">{selectedSurfaceIndex != null && <button type="button" className="geometry-reset geometry-show-all" onClick={clearSurfaceFilter}>VER TODOS LOS RAYOS</button>}<button type="button" className="geometry-reset" onClick={() => setExpanded(value => !value)}>{expanded ? 'CERRAR AMPLIACIÓN' : 'AMPLIAR VISOR'}</button><button type="button" className="geometry-reset" onClick={toggleFullscreen}>{isFullscreen ? 'SALIR PANTALLA' : 'PANTALLA COMPLETA'}</button><button type="button" className="geometry-reset" onClick={() => resetViewRef.current()}>AJUSTAR VISTA</button></div></div>
    <div className="geometry-view-layout"><div ref={canvasRef} className="geometry-canvas" role="img" aria-label="Visor 3D de lente, LED y rayos"><div className="geometry-canvas-help">ARRASTRAR: ROTAR · RUEDA: ZOOM · CLIC: SELECCIONAR · SHIFT: SUPERFICIE</div></div><GeometryAnglePanel data={data} ray={selectedRay} rayIndex={selectedRayIndex} /></div>
    <div className="geometry-view-controls"><label><span>LED visible</span><select value={ledSelection} onChange={event => setLedSelection(event.target.value === 'all' ? 'all' : Number(event.target.value) as 0 | 1 | 2)}><option value="all">Todos los LED ({details.length.toLocaleString('es-ES')})</option><option value="0">LED 1 ({ledCounts[0].toLocaleString('es-ES')})</option><option value="1">LED 2 ({ledCounts[1].toLocaleString('es-ES')})</option><option value="2">LED 3 ({ledCounts[2].toLocaleString('es-ES')})</option></select></label><label><span>Rayos visibles</span><select value={Math.min(rayLimit, maxRayCount || rayLimit)} disabled={!maxRayCount} onChange={event => setRayLimit(Number(event.target.value))}>{rayOptions.map(value => <option key={value} value={value}>{value.toLocaleString('es-ES')}</option>)}</select></label><label><span>Color por</span><select value={colorMode} onChange={event => setColorMode(event.target.value as 'status' | 'led')}><option value="status">Estado óptico</option><option value="led">LED de origen</option></select></label><label className="geometry-check"><input type="checkbox" checked={showRays} onChange={event => setShowRays(event.target.checked)} /> rayos</label><label className="geometry-check"><input type="checkbox" checked={showLens} onChange={event => setShowLens(event.target.checked)} /> lente</label><label className="geometry-check"><input type="checkbox" checked={showLeds} onChange={event => setShowLeds(event.target.checked)} /> LED</label><label className="geometry-check"><input type="checkbox" checked={showGrid} onChange={event => setShowGrid(event.target.checked)} /> rejilla</label><label className="geometry-check"><input type="checkbox" checked={showAxes} onChange={event => setShowAxes(event.target.checked)} /> ejes</label></div>
      <div className="geometry-surface-filter"><span>{selectedSurfaceLabel ? `FILTRANDO RAYOS QUE TOCAN ${selectedSurfaceLabel} · ENTRADA, SALIDA O TIR` : 'CLIC SOBRE LA LENTE PARA FILTRAR · SHIFT FUERZA SUPERFICIE'}</span><button type="button" disabled={selectedSurfaceIndex == null} onClick={clearSurfaceFilter}>Quitar filtro</button></div>
      <div className="geometry-color-legend"><span>Color: {colorMode === 'status' ? 'estado óptico' : 'LED de origen'}</span>{colorMode === 'status' ? (Object.keys(RAY_STATUS_LABELS) as PreviewRayStatus[]).map(status => <span key={status}><i style={{ background: RAY_STATUS_COLORS[status] }} />{RAY_STATUS_LABELS[status]}</span>) : LED_COLORS.map((color, index) => <span key={color}><i style={{ background: color }} />LED {index + 1}</span>)}</div>
      <div className="geometry-status-filters">{(Object.keys(RAY_STATUS_LABELS) as PreviewRayStatus[]).map(status => <label key={status}><input type="checkbox" checked={statusVisibility[status]} onChange={() => toggleStatus(status)} /><i style={{ background: RAY_STATUS_COLORS[status] }} />{RAY_STATUS_LABELS[status]} <small>{data.trace.preview_status_counts?.[status] ?? 0}</small></label>)}<span>{Math.min(rayLimit, selectedCount).toLocaleString('es-ES')} visibles activos</span></div>
    <div className="geometry-stats"><span><b>{data.geometry.lens_triangles?.toLocaleString('es-ES') || '—'}</b> triángulos lente</span><span><b>{data.trace.transmission_pct.toFixed(2)}%</b> transmisión</span><span><b>{data.trace.total_internal_reflection_count.toLocaleString('es-ES')}</b> TIR</span><span><b>{data.ldt.peak_c_deg?.toFixed(0) ?? '—'}° / {data.ldt.peak_gamma_deg?.toFixed(0) ?? '—'}°</b> pico C / gamma</span></div>
  </section>;
}

function ReferenceComparison({ calculated, reference }: { calculated: Metrics; reference: Metrics }) {
  const rows = [
    ['Lavg', 'cd/m²', calculated.lavg_cd_m2, reference.lavg_cd_m2],
    ['Uo', '', calculated.uo, reference.uo],
    ['Ul', '', calculated.ul, reference.ul],
    ['TI', '%', calculated.ti_pct, reference.ti_pct],
    ['REI', '', calculated.rei, reference.rei],
  ] as const;
  return <section className="reference-comparison"><div className="card-title"><span>COMPARACIÓN VIAL / LDT COMPLETO</span><small>modelo calculado frente a referencia DIALux</small></div><div className="reference-comparison-grid"><div><b>Calculado por grupos</b><small>8 fuentes virtuales</small></div><div><b>LDT completo</b><small>fotometría cargada</small></div></div><table><thead><tr><th>Métrica</th><th>Calculado</th><th>Referencia</th><th>Diferencia</th></tr></thead><tbody>{rows.map(([label, unit, calculatedValue, referenceValue]) => <tr key={label}><th>{label} <small>{unit}</small></th><td>{calculatedValue.toFixed(3)}</td><td>{referenceValue.toFixed(3)}</td><td>{(calculatedValue - referenceValue).toFixed(3)}</td></tr>)}</tbody></table><p>La referencia se evalúa con su propio flujo declarado y no modifica la optimización.</p></section>;
}

function NormativeGraph({ xs, profiles, worstLane, selectedLane, onLaneChange }: { xs: number[]; profiles: LaneProfile[]; worstLane: number; selectedLane: number; onLaneChange: (lane: number) => void }) {
  const width = 920;
  const height = 260;
  const left = 56;
  const top = 24;
  const plotWidth = 820;
  const plotHeight = 178;
  const allValues = profiles.flatMap(profile => profile.luminance_cd_m2);
  const maximum = Math.max(...allValues, 1);
  const xPosition = (index: number) => left + (xs.length > 1 ? index / (xs.length - 1) : .5) * plotWidth;
  const yPosition = (value: number) => top + plotHeight - (value / maximum) * plotHeight;
  const points = (profile: LaneProfile) => profile.luminance_cd_m2.map((value, index) => `${xPosition(index)},${yPosition(value)}`).join(' ');
  return <div className="normative-card"><div className="card-title"><span>GRÁFICA NORMATIVA / LUMINANCIA LONGITUDINAL</span><small>peor carril: {worstLane + 1}</small></div><div className="normative-toolbar"><label><span>Carril visualizado en el mapa</span><select value={Math.min(selectedLane, Math.max(profiles.length - 1, 0))} onChange={event => onLaneChange(Number(event.target.value))}>{profiles.map(profile => <option key={profile.lane_index} value={profile.lane_index}>Carril {profile.lane_index + 1}</option>)}</select></label><span className="normative-note">La curva gruesa es el peor carril normativo</span></div><svg className="normative-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Perfil longitudinal normativo del carril ${worstLane + 1}`}><rect width={width} height={height} fill="#fbfcf9" />{[0, .25, .5, .75, 1].map(level => <g key={level}><line x1={left} y1={yPosition(maximum * level)} x2={left + plotWidth} y2={yPosition(maximum * level)} stroke="#dce5dc" strokeWidth="1" /><text x={left - 8} y={yPosition(maximum * level) + 3} textAnchor="end" fill="#819087" fontSize="9">{(maximum * level).toFixed(1)}</text></g>)}{profiles.filter(profile => profile.lane_index !== worstLane).map(profile => <polyline key={`lane-profile-${profile.lane_index}`} points={points(profile)} fill="none" stroke={profile.lane_index === selectedLane ? "#ef7348" : "#aabbb0"} strokeWidth={profile.lane_index === selectedLane ? "2" : "1"} opacity=".7" />)}{profiles[worstLane] && <polyline points={points(profiles[worstLane])} fill="none" stroke="#173e36" strokeWidth="3" />}{xs.map((value, index) => <text key={value} x={xPosition(index)} y={top + plotHeight + 20} textAnchor="middle" fill="#819087" fontSize="9">{value.toFixed(1)}</text>)}<line x1={left} y1={top + plotHeight} x2={left + plotWidth} y2={top + plotHeight} stroke="#173e36" /><text x={left + plotWidth} y={top + plotHeight + 38} textAnchor="end" fill="#52685a" fontSize="10">x / longitudinal (m)</text><text x={left - 8} y={top + 8} textAnchor="end" fill="#52685a" fontSize="10">L / cd/m²</text></svg></div>;
}

function RoadAnimation({ width, height, spacing, edgeOffset, arrangement }: { width: number; height: number; spacing: number; edgeOffset: number; arrangement: string }) {
  const twoRows = arrangement !== 'unilateral';
  const laneCount = Math.max(1, Math.round(width / 3.5));
  const roadTop = 92;
  const roadBottom = 278;
  const roadLeft = 70;
  const roadRight = 830;
  const roadWidth = roadBottom - roadTop;
  const trackOffset = Math.min(42, Math.max(10, edgeOffset * 18));
  const posts = Array.from({ length: 7 }, (_, index) => roadLeft + 30 + index * 124);
  return <div className="road-video-card"><div className="road-video-head"><span>PLANTA DE CALZADA / ROAD MOTION</span><small>eje longitudinal horizontal</small></div><svg className="road-video" viewBox="0 0 900 370" role="img" aria-label="Animación en planta de la carretera">
    <defs><linearGradient id="roadVideoSurface" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stopColor="#61776e" /><stop offset="1" stopColor="#203f38" /></linearGradient><linearGradient id="roadVideoSide" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#35594e" /><stop offset="1" stopColor="#14322d" /></linearGradient><filter id="roadVideoGlow"><feGaussianBlur stdDeviation="4" /></filter><marker id="roadVideoArrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10Z" fill="#b9e77a" /></marker></defs>
    <rect width="900" height="370" fill="#153b34" /><path d="M0 55H900M0 150H900M0 245H900M0 340H900" stroke="#326055" strokeWidth="1" opacity=".45" /><rect x={roadLeft} y={roadTop} width={roadRight - roadLeft} height={roadWidth} rx="2" fill="url(#roadVideoSurface)" stroke="#94b1a0" strokeWidth="2" /><path d={`M${roadLeft} ${roadBottom}H${roadRight}`} stroke="#b9e77a" strokeWidth="2" opacity=".85" /><path d={`M${roadLeft} ${roadTop}H${roadRight}`} stroke="#b9e77a" strokeWidth="2" opacity=".85" />
    {Array.from({ length: laneCount - 1 }, (_, index) => { const y = roadTop + ((index + 1) / laneCount) * roadWidth; return <path key={`lane-${index}`} d={`M${roadLeft} ${y}H${roadRight}`} stroke="#d9e8d7" strokeWidth="2" strokeDasharray="16 13" opacity=".7" />; })}
    <g className="road-motion-lines">{Array.from({ length: 7 }, (_, index) => <path key={`motion-${index}`} d={`M${120 + index * 115} ${roadTop + 25 + (index % 2) * 55}h${28 + (index % 3) * 12}`} stroke="#b9e77a" strokeWidth="2" strokeLinecap="round" opacity=".55" />)}</g>
    {posts.map((x, index) => { const staggered = arrangement === 'bilateral_staggered'; const xTop = staggered ? x + 58 : x; const xBottom = x; return <g key={`post-${index}`} className="road-video-luminaire" style={{ animationDelay: `${-(index * .55)}s` }}>
      <line x1={xTop} y1={roadTop - trackOffset} x2={xTop} y2={roadTop - 20 - trackOffset} stroke="#aec4b3" strokeWidth="2" /><line x1={xTop} y1={roadTop - 20 - trackOffset} x2={xTop + 14} y2={roadTop - 20 - trackOffset} stroke="#b9e77a" strokeWidth="2" /><circle cx={xTop + 14} cy={roadTop - 20 - trackOffset} r="5" fill="#b9e77a" /><circle className="road-video-glow" cx={xTop + 14} cy={roadTop - 20 - trackOffset} r="14" fill="#b9e77a" opacity=".3" filter="url(#roadVideoGlow)" />
      {twoRows && <><line x1={xBottom} y1={roadBottom + trackOffset} x2={xBottom} y2={roadBottom + 20 + trackOffset} stroke="#aec4b3" strokeWidth="2" /><line x1={xBottom} y1={roadBottom + 20 + trackOffset} x2={xBottom - 14} y2={roadBottom + 20 + trackOffset} stroke="#b9e77a" strokeWidth="2" /><circle cx={xBottom - 14} cy={roadBottom + 20 + trackOffset} r="5" fill="#b9e77a" /><circle className="road-video-glow" cx={xBottom - 14} cy={roadBottom + 20 + trackOffset} r="14" fill="#b9e77a" opacity=".3" filter="url(#roadVideoGlow)" /></>}
    </g>; })}
    <line x1="118" y1="326" x2="318" y2="326" stroke="#b9e77a" strokeWidth="1.5" markerStart="url(#roadVideoArrow)" markerEnd="url(#roadVideoArrow)" /><text x="218" y="344" fill="#dcebd7" fontSize="11" textAnchor="middle" fontFamily="DM Mono, monospace">S = {spacing.toFixed(1)} m</text><text x="42" y="196" fill="#b9e77a" fontSize="11" fontFamily="DM Mono, monospace" transform="rotate(-90 42 196)">W = {width.toFixed(1)} m</text><text x="714" y="28" fill="#b9e77a" fontSize="11" fontFamily="DM Mono, monospace">H = {height.toFixed(2)} m · OFFSET = {edgeOffset.toFixed(1)} m</text>
  </svg></div>;
}

function LuminanceMap(props: { grid: VisualGrid; referenceGrid?: VisualGrid; groupLdt?: LdtDiagnostic; luminaireLdt?: LdtDiagnostic; referenceLdt?: LdtDiagnostic; luminaireHeight: number; carriagewayWidth: number; spacing: number; edgeOffset: number; arrangement: string; selectedLane: number; onLaneChange: (lane: number) => void }) {
  const [metric, setMetric] = useState<MapMetric>('luminance');
  const referenceSelected = metric.startsWith('reference-');
  const activeGrid = referenceSelected && props.referenceGrid ? props.referenceGrid : props.grid;
  const laneCount = activeGrid.lane_grids?.length || 1;
  const activeMetric = referenceSelected ? metric.replace('reference-', '') as 'luminance' | 'illuminance' : metric;
  return <div className="luminance-map-shell"><div className="map-toolbar"><label><span>Magnitud</span><select value={metric} onChange={event => setMetric(event.target.value as MapMetric)}><option value="luminance">Calculada · luminancia / cd/m²</option><option value="illuminance">Calculada · iluminancia / lux</option>{props.referenceGrid && <><option value="reference-luminance">Referencia LDT · luminancia / cd/m²</option><option value="reference-illuminance">Referencia LDT · iluminancia / lux</option></>}</select></label>{laneCount > 1 && <label><span>Carril del observador</span><select value={Math.min(props.selectedLane, laneCount - 1)} onChange={event => props.onLaneChange(Number(event.target.value))}>{Array.from({ length: laneCount }, (_, index) => <option key={index} value={index}>Carril {index + 1}</option>)}</select></label>}</div><LuminanceMapSvg {...props} grid={activeGrid} groupLdt={referenceSelected ? undefined : props.groupLdt} luminaireLdt={referenceSelected ? props.referenceLdt : props.luminaireLdt} metric={activeMetric} /> </div>;
}

function LuminanceMapSvg({ grid, groupLdt, luminaireLdt, luminaireHeight, carriagewayWidth, spacing: interdistance, edgeOffset, arrangement, selectedLane, metric }: { grid: VisualGrid; groupLdt?: LdtDiagnostic; luminaireLdt?: LdtDiagnostic; luminaireHeight: number; carriagewayWidth: number; spacing: number; edgeOffset: number; arrangement: string; selectedLane: number; metric: MapMetric }) {
  const laneGrids = grid.lane_grids || [];
  const activeLane = Math.min(selectedLane, Math.max(laneGrids.length - 1, 0));
  const values = metric === 'illuminance' ? grid.illuminance_lx : laneGrids[activeLane]?.luminance_cd_m2 || grid.luminance_cd_m2;
  const xCount = values.length;
  const yCount = values[0]?.length ?? 0;
  const allValues = values.flat();
  const minimum = allValues.length ? Math.min(...allValues) : 0;
  const maximum = Math.max(...allValues, 1);
  const range = Math.max(maximum - minimum, 1e-9);
  const width = 920;
  const height = 340;
  const left = 60;
  const top = 24;
  const plotWidth = 820;
  const plotHeight = 250;
  const spacing = interdistance * (arrangement === 'bilateral_staggered' ? 1.5 : 1);
  const ldtRadiusScale = luminaireLdt ? interdistance * .12 : 0;
  const ldtExtentX = ldtRadiusScale;
  const ldtExtentY = ldtRadiusScale;
  const mapMinX = -ldtExtentX;
  const mapMaxX = spacing + ldtExtentX;
  const mapMinY = -Math.max(edgeOffset, .15) - ldtExtentY;
  const mapMaxY = carriagewayWidth + Math.max(edgeOffset, .15) + ldtExtentY;
  const mapRangeX = mapMaxX - mapMinX;
  const mapRangeY = mapMaxY - mapMinY;
  const mapScale = Math.min(plotWidth / mapRangeX, plotHeight / mapRangeY);
  const mapDrawWidth = mapRangeX * mapScale;
  const mapDrawHeight = mapRangeY * mapScale;
  const mapLeft = left + (plotWidth - mapDrawWidth) / 2;
  const mapTop = top + (plotHeight - mapDrawHeight) / 2;
  const laneWidths = grid.lane_widths_m || [];
  const laneCentres = grid.lane_centres_m || [];
  const observerY = laneCentres[activeLane] ?? carriagewayWidth / 2;
  const [showLdt, setShowLdt] = useState(false);
  const showGroupMaxima = true;
  const sample = (u: number, v: number) => {
    const x = Math.max(0, Math.min(xCount - 1, u * (xCount - 1)));
    const y = Math.max(0, Math.min(yCount - 1, v * (yCount - 1)));
    const x0 = Math.floor(x); const x1 = Math.min(xCount - 1, x0 + 1);
    const y0 = Math.floor(y); const y1 = Math.min(yCount - 1, y0 + 1);
    const tx = x - x0; const ty = y - y0;
    return (1 - tx) * ((1 - ty) * values[x0][y0] + ty * values[x0][y1]) + tx * ((1 - ty) * values[x1][y0] + ty * values[x1][y1]);
  };
  const denseX = Math.max(24, (xCount - 1) * 8 + 1);
  const denseY = Math.max(24, (yCount - 1) * 8 + 1);
  const dataMinX = 0;
  const dataMaxX = spacing;
  const dataMinY = Math.min(...grid.ys_m, 0);
  const dataMaxY = Math.max(...grid.ys_m, carriagewayWidth);
  const dataPx = (u: number) => xPosition(dataMinX + u * (dataMaxX - dataMinX));
  const dataPy = (v: number) => yPosition(dataMinY + v * (dataMaxY - dataMinY));
  const px = (u: number) => mapLeft + u * mapDrawWidth;
  const py = (v: number) => mapTop + v * mapDrawHeight;
  const xPosition = (x: number) => px((x - mapMinX) / mapRangeX);
  const yPosition = (y: number) => py((y - mapMinY) / mapRangeY);
  const color = (value: number) => `hsl(${220 - ((value - minimum) / range) * 220} 76% 54%)`;
  const surface = [] as JSX.Element[];
  for (let x = 0; x < denseX - 1; x += 1) for (let y = 0; y < denseY - 1; y += 1) {
    const u = x / (denseX - 1); const v = y / (denseY - 1);
    const value = sample(u + 1 / (denseX - 1) / 2, v + 1 / (denseY - 1) / 2);
    surface.push(<rect key={`surface-${x}-${y}`} x={dataPx(u)} y={dataPy(v)} width={(dataMaxX - dataMinX) / (denseX - 1) * mapScale + .5} height={(dataMaxY - dataMinY) / (denseY - 1) * mapScale + .5} fill={color(value)} />);
  }
  const contourPaths = [] as JSX.Element[];
  const levels = Array.from({ length: 6 }, (_, index) => minimum + range * (index + 1) / 7);
  levels.forEach(level => {
    for (let x = 0; x < denseX - 1; x += 1) for (let y = 0; y < denseY - 1; y += 1) {
      const u0 = x / (denseX - 1); const u1 = (x + 1) / (denseX - 1); const v0 = y / (denseY - 1); const v1 = (y + 1) / (denseY - 1);
      const cornerValues = [sample(u0, v0), sample(u1, v0), sample(u1, v1), sample(u0, v1)];
       const corners = [[dataPx(u0), dataPy(v0)], [dataPx(u1), dataPy(v0)], [dataPx(u1), dataPy(v1)], [dataPx(u0), dataPy(v1)]];
      const intersections: string[] = [];
      for (let edge = 0; edge < 4; edge += 1) {
        const next = (edge + 1) % 4;
        if ((cornerValues[edge] < level) === (cornerValues[next] < level)) continue;
        const fraction = (level - cornerValues[edge]) / (cornerValues[next] - cornerValues[edge]);
       intersections.push(`${corners[edge][0] + (corners[next][0] - corners[edge][0]) * fraction},${corners[edge][1] + (corners[next][1] - corners[edge][1]) * fraction}`);
      }
       if (intersections.length >= 2) for (let i = 0; i + 1 < intersections.length; i += 2) contourPaths.push(<path key={`contour-${level}-${x}-${y}-${i}`} d={`M${intersections[i]}L${intersections[i + 1]}`} stroke={color(level)} strokeWidth="1.2" fill="none" opacity=".9" />);
    }
  });
  let laneStart = 0;
  laneWidths.slice(0, -1).forEach((laneWidth, index) => {
    laneStart += laneWidth;
    contourPaths.push(<path key={`lane-boundary-${index}`} d={`M${xPosition(mapMinX)} ${yPosition(laneStart)}H${xPosition(mapMaxX)}`} stroke="#d7e2d5" strokeWidth="1" strokeDasharray="5 5" />);
  });
  const observerX = mapMinX + (mapMaxX - mapMinX) * .04;
  const observerArrowEnd = observerX + (mapMaxX - mapMinX) * .09;
  contourPaths.push(<line key="observer-line" x1={xPosition(observerX)} y1={yPosition(observerY)} x2={xPosition(observerArrowEnd)} y2={yPosition(observerY)} stroke="#173e36" strokeWidth="2.2" />);
  contourPaths.push(<polygon key="observer-arrow" points={`${xPosition(observerArrowEnd)},${yPosition(observerY)} ${xPosition(observerArrowEnd) - 8},${yPosition(observerY) - 4} ${xPosition(observerArrowEnd) - 8},${yPosition(observerY) + 4}`} fill="#173e36" />);
  contourPaths.push(<text key="observer-label" x={xPosition(observerX)} y={yPosition(observerY) - 8} fill="#173e36" fontSize="9" fontFamily="DM Mono, monospace">OBSERVADOR {grid.observer_distance_m ? `· ${grid.observer_distance_m.toFixed(0)} m` : ''}</text>);
    // C0/C180 follow the road; the right row is rotated 180 degrees so C90
    // points into the carriageway on both rows.
    const luminairePositions = [
      { x: 0, y: -edgeOffset, label: 'L1', orientation: 0 },
      { x: interdistance, y: -edgeOffset, label: 'L2', orientation: 0 },
     ...(arrangement === 'unilateral' ? [] : [
        { x: arrangement === 'bilateral_staggered' ? interdistance / 2 : 0, y: carriagewayWidth + edgeOffset, label: 'L3', orientation: 180 },
        { x: arrangement === 'bilateral_staggered' ? interdistance * 1.5 : interdistance, y: carriagewayWidth + edgeOffset, label: 'L4', orientation: 180 },
     ]),
   ];
   const ldtShape = (luminaire: typeof luminairePositions[number]) => {
     if (!luminaireLdt) return '';
     const maxIntensity = Math.max(luminaireLdt.max_intensity_cd_per_klm, 1);
     const downwardGammaIndexes = luminaireLdt.gamma_angles_deg
       .map((gamma, index) => gamma <= 90 ? index : -1)
       .filter(index => index >= 0);
     return luminaireLdt.c_angles_deg.map((angle, cIndex) => {
       const intensity = Math.max(...downwardGammaIndexes.map(gammaIndex => luminaireLdt.intensities_cd_per_klm[cIndex][gammaIndex]), 0);
        const radius = Math.sqrt(intensity / maxIntensity) * ldtRadiusScale;
        const radians = (angle + luminaire.orientation) * Math.PI / 180;
        return `${xPosition(luminaire.x + Math.cos(radians) * radius)},${yPosition(luminaire.y + Math.sin(radians) * radius)}`;
     }).join(' ');
    };
   const maxGamma = groupLdt?.peak_gamma_deg ?? 0;
   const maxLocalC = groupLdt?.peak_c_deg ?? 0;
   const rayToMapEdge = (x: number, y: number, dx: number, dy: number) => {
     const distances = [
       dx > 0 ? (mapMaxX - x) / dx : dx < 0 ? (mapMinX - x) / dx : Infinity,
       dy > 0 ? (mapMaxY - y) / dy : dy < 0 ? (mapMinY - y) / dy : Infinity,
     ].filter(distance => distance >= 0 && Number.isFinite(distance));
     return Math.min(...distances, Math.hypot(mapRangeX, mapRangeY));
   };
   const maxIntensityLines = showGroupMaxima && groupLdt ? luminairePositions.flatMap((luminaire, luminaireIndex) => GROUP_ANGLES.map((groupAngle, groupIndex) => {
     const direction = (maxLocalC + GROUP_C_ROTATION_DEG + groupAngle + luminaire.orientation) * Math.PI / 180;
     const dx = Math.cos(direction);
     const dy = Math.sin(direction);
     const physicalReach = maxGamma >= 89.5 ? Infinity : luminaireHeight * Math.tan(maxGamma * Math.PI / 180);
     const reach = Math.min(physicalReach, rayToMapEdge(luminaire.x, luminaire.y, dx, dy));
     const endX = luminaire.x + dx * reach;
     const endY = luminaire.y + dy * reach;
     const displayC = ((maxLocalC + GROUP_C_ROTATION_DEG + groupAngle + luminaire.orientation) % 360 + 360) % 360;
     return <g key={`group-max-${luminaireIndex}-${groupIndex}`} className="map-group-max"><title>{`${luminaire.label} · G${groupIndex + 1} · C${displayC.toFixed(1)}° · gamma ${maxGamma.toFixed(1)}°`}</title><line x1={xPosition(luminaire.x)} y1={yPosition(luminaire.y)} x2={xPosition(endX)} y2={yPosition(endY)} /><circle cx={xPosition(endX)} cy={yPosition(endY)} r="2" /></g>;
    })) : [];
    const ldtCells = [...maxIntensityLines, ...(showLdt && luminaireLdt ? luminairePositions.map((luminaire, index) => <polygon key={`ldt-azimuth-${index}`} className="map-ldt-shape" points={ldtShape(luminaire)} />) : [])];
   const ldtVisualScale = .12;
  return <div className="luminance-map"><div className="heatmap-labels"><span>L / cd/m²</span><span>rango {minimum.toFixed(2)} — {maximum.toFixed(2)} cd/m²</span></div><label className="ldt-map-toggle"><input type="checkbox" checked={showLdt} onChange={event => setShowLdt(event.target.checked)} disabled={!luminaireLdt} /> Mostrar vista cenital del LDT completo <small>(escala visual ×{ldtVisualScale.toFixed(2)})</small></label><svg className="luminance-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Mapa de luminancia con isocurvas y luminarias"><rect width={width} height={height} fill="#eef3ec" />{surface}{contourPaths}<rect x={xPosition(0)} y={yPosition(0)} width={xPosition(spacing) - xPosition(0)} height={yPosition(carriagewayWidth) - yPosition(0)} fill="none" stroke="#173e36" strokeWidth="1.5" /><path d={`M${left} ${top + plotHeight}H${left + plotWidth}M${left} ${top}V${top + plotHeight}`} stroke="#173e36" strokeWidth="1" /><text x={left + plotWidth - 8} y={top + plotHeight + 24} textAnchor="end" fill="#52685a" fontSize="10">x / longitudinal</text><text x={left - 8} y={top + 10} textAnchor="end" fill="#52685a" fontSize="10">y / transversal</text>{values.flatMap((row, x) => row.map((value, y) => { const u = xCount > 1 ? (grid.xs_m[x] - mapMinX) / (mapMaxX - mapMinX) : .5; const v = yCount > 1 ? (grid.ys_m[y] - mapMinY) / (mapMaxY - mapMinY) : .5; return <g key={`measurement-${x}-${y}`}><circle cx={px(u)} cy={py(v)} r="3.2" fill="#fff" stroke="#173e36" strokeWidth="1" /><text x={px(u) + 5} y={py(v) - 5} fill="#173e36" fontSize="9" fontFamily="DM Mono, monospace" paintOrder="stroke" stroke="#eef3ec" strokeWidth="3">{value.toFixed(2)}</text></g>; }))}{ldtCells}{luminairePositions.map((luminaire, index) => <g key={`luminaire-${index}`} className="map-luminaire"><line x1={xPosition(luminaire.x)} y1={yPosition(luminaire.y)} x2={xPosition(luminaire.x)} y2={yPosition(luminaire.y < 0 ? 0 : carriagewayWidth)} /><circle cx={xPosition(luminaire.x)} cy={yPosition(luminaire.y)} r="7" /><text x={xPosition(luminaire.x) + 10} y={yPosition(luminaire.y) + 4}>{luminaire.label}</text></g>)}</svg><div className="heatmap-caption"><span>puntos blancos = mediciones originales</span><span>cenital LDT completo · escala visual de orientación · disposición {arrangement}</span></div></div>;
}

function LdtDiagnostics({ title, diagnostic, showPlaneProfiles = false }: { title: string; diagnostic: LdtDiagnostic; showPlaneProfiles?: boolean }) {
  return <section className="ldt-diagnostic">
    <div className="card-title"><span>{title}</span><small>{diagnostic.name} · {diagnostic.c_angles_deg.length} C × {diagnostic.gamma_angles_deg.length} gamma · pico C{diagnostic.peak_c_deg?.toFixed(1) ?? '—'} / gamma {diagnostic.peak_gamma_deg?.toFixed(1) ?? '—'}°</small></div>
    <div className="ldt-diagnostic-grid">
      <LdtSurface diagnostic={diagnostic} />
      <div className="ldt-pair-panel">
        <div className={`symmetry-banner ${diagnostic.symmetric ? 'good' : 'bad'}`}><b>{diagnostic.symmetric ? 'SIMÉTRICO' : 'ASIMÉTRICO'}</b><span>tolerancia ±{diagnostic.symmetry_tolerance_pct.toFixed(1)} %</span></div>
        <div className="ldt-pair-list">{diagnostic.pairs.map(pair => <div className={`ldt-pair ${pair.symmetric ? '' : 'mismatch'}`} key={`${pair.c_deg}-${pair.mirror_c_deg}`}><span>C {pair.c_deg.toFixed(2)}° ↔ {pair.mirror_c_deg.toFixed(2)}°</span><b>{pair.max_difference_pct.toFixed(1)} %</b><small>gamma {pair.worst_gamma_deg.toFixed(0)}° · {pair.symmetric ? 'OK' : 'NO SIMÉTRICO'}</small></div>)}</div>
      </div>
    </div>
     {showPlaneProfiles && <LdtPlaneProfiles diagnostic={diagnostic} />}
     <LdtGridTable diagnostic={diagnostic} />
   </section>;
}

const LDT_PLANES = [0, 90, 180, 280];
const LDT_PLANE_COLORS = ['#ef7348', '#173e36', '#6f8f7d', '#b07b37'];

function sampleLdtPlane(diagnostic: LdtDiagnostic, c: number, gamma: number) {
  const axis = diagnostic.c_angles_deg;
  const normalized = ((c % 360) + 360) % 360;
  const step = axis.length > 1 ? axis[1] - axis[0] : 360;
  const circular = axis[axis.length - 1] - axis[0] + step >= 360 - 1e-6;
  if (!circular && (normalized < axis[0] || normalized > axis[axis.length - 1])) return 0;
  const query = circular && normalized < axis[0] ? normalized + 360 : normalized;
  let left = 0;
  while (left < axis.length - 1 && axis[left + 1] <= query) left += 1;
  const right = left === axis.length - 1 ? 0 : left + 1;
  const upper = right === 0 ? axis[0] + 360 : axis[right];
  const fraction = (query - axis[left]) / Math.max(upper - axis[left], 1e-9);
  const leftValue = pchipValue(diagnostic.gamma_angles_deg, diagnostic.intensities_cd_per_klm[left], gamma);
  const rightValue = pchipValue(diagnostic.gamma_angles_deg, diagnostic.intensities_cd_per_klm[right], gamma);
  return Math.max(0, (1 - fraction) * leftValue + fraction * rightValue);
}

function LdtPlaneProfiles({ diagnostic }: { diagnostic: LdtDiagnostic }) {
  const gammaMax = diagnostic.gamma_angles_deg[diagnostic.gamma_angles_deg.length - 1] || 90;
  const gammaStep = Math.max(1, Math.min(5, diagnostic.gamma_angles_deg[1] - diagnostic.gamma_angles_deg[0] || 5));
  const gammas = Array.from({ length: Math.round(gammaMax / gammaStep) + 1 }, (_, index) => Math.min(gammaMax, index * gammaStep));
  const profiles = LDT_PLANES.map((plane, index) => ({ plane, color: LDT_PLANE_COLORS[index], values: gammas.map(gamma => sampleLdtPlane(diagnostic, plane, gamma)) }));
  const maximum = Math.max(...profiles.flatMap(profile => profile.values), 1);
  const width = 720;
  const height = 260;
  const left = 48;
  const top = 22;
  const plotWidth = 625;
  const plotHeight = 178;
  const xPosition = (gamma: number) => left + (gamma / Math.max(gammaMax, 1)) * plotWidth;
  const yPosition = (value: number) => top + plotHeight - (value / maximum) * plotHeight;
  const points = (values: number[]) => values.map((value, index) => `${xPosition(gammas[index])},${yPosition(value)}`).join(' ');
  return <section className="ldt-plane-card">
    <div className="ldt-plane-heading"><span>PLANOS FOTOMÉTRICOS / ORIENTACIÓN</span><small>gamma 0–{gammaMax.toFixed(0)}° · cd/klm</small></div>
    <svg className="ldt-plane-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Perfiles fotométricos C0 C90 C180 y C280">
      <rect width={width} height={height} fill="#fbfcf9" />
      {[0, .25, .5, .75, 1].map(level => <g key={level}><line x1={left} y1={yPosition(maximum * level)} x2={left + plotWidth} y2={yPosition(maximum * level)} stroke="#dce5dc" strokeWidth="1" /><text x={left - 8} y={yPosition(maximum * level) + 3} textAnchor="end" fill="#819087" fontSize="9">{(maximum * level).toFixed(0)}</text></g>)}
      {[0, 30, 60, 90].filter(value => value <= gammaMax).map(gamma => <g key={gamma}><line x1={xPosition(gamma)} y1={top} x2={xPosition(gamma)} y2={top + plotHeight} stroke="#eef2ec" strokeWidth="1" /><text x={xPosition(gamma)} y={top + plotHeight + 18} textAnchor="middle" fill="#819087" fontSize="9">{gamma}°</text></g>)}
      <line x1={left} y1={top + plotHeight} x2={left + plotWidth} y2={top + plotHeight} stroke="#173e36" strokeWidth="1" />
      {profiles.map(profile => <polyline key={profile.plane} points={points(profile.values)} fill="none" stroke={profile.color} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />)}
      <text x={left + plotWidth} y={top + plotHeight + 38} textAnchor="end" fill="#52685a" fontSize="10">gamma / grados</text>
      <text x="12" y="14" fill="#52685a" fontSize="9">cd/klm</text>
    </svg>
    <div className="ldt-plane-legend">{profiles.map(profile => <span key={profile.plane}><i style={{ background: profile.color }} />C{profile.plane} · {Math.max(...profile.values).toFixed(0)} cd/klm</span>)}</div>
  </section>;
}

function pchipValue(xs: number[], ys: number[], target: number) {
  if (xs.length < 2 || target <= xs[0]) return ys[0];
  if (target >= xs[xs.length - 1]) return ys[ys.length - 1];
  const h = xs.slice(1).map((value, index) => value - xs[index]);
  const slopes = h.map((step, index) => (ys[index + 1] - ys[index]) / step);
  const tangents = ys.map((_, index) => {
    if (index === 0) return slopes[0];
    if (index === ys.length - 1) return slopes[slopes.length - 1];
    if (slopes[index - 1] * slopes[index] <= 0) return 0;
    return (slopes[index - 1] + slopes[index]) / 2;
  });
  const index = Math.max(0, xs.findIndex(value => value > target) - 1);
  const t = (target - xs[index]) / h[index];
  const t2 = t * t;
  const t3 = t2 * t;
  return (2 * t3 - 3 * t2 + 1) * ys[index]
    + (t3 - 2 * t2 + t) * h[index] * tangents[index]
    + (-2 * t3 + 3 * t2) * ys[index + 1]
    + (t3 - t2) * h[index] * tangents[index + 1];
}

function smoothLdtDiagnostic(diagnostic: LdtDiagnostic): LdtDiagnostic {
  const cStep = 2.5;
  const gammaStep = Math.max(2.5, Math.min(5, diagnostic.gamma_angles_deg[1] - diagnostic.gamma_angles_deg[0] || 2.5));
  const cAngles = Array.from({ length: Math.round(360 / cStep) }, (_, index) => index * cStep);
  const gammaMax = diagnostic.gamma_angles_deg[diagnostic.gamma_angles_deg.length - 1];
  const gammaCount = Math.round(gammaMax / gammaStep) + 1;
  const gammaAngles = Array.from({ length: gammaCount }, (_, index) => Math.min(gammaMax, index * gammaStep));
  const sample = (c: number, gamma: number) => {
    const axis = diagnostic.c_angles_deg;
    const normalized = ((c % 360) + 360) % 360;
    const step = axis.length > 1 ? axis[1] - axis[0] : 360;
    const circular = axis[axis.length - 1] - axis[0] + step >= 360 - 1e-6;
    if (!circular && (normalized < axis[0] || normalized > axis[axis.length - 1])) return 0;
    let left = 0;
    const query = circular && normalized < axis[0] ? normalized + 360 : normalized;
    while (left < axis.length - 1 && axis[left + 1] <= query) left += 1;
    const right = left === axis.length - 1 ? 0 : left + 1;
    const upper = right === 0 ? axis[0] + 360 : axis[right];
    const fraction = (query - axis[left]) / (upper - axis[left]);
    const leftValue = pchipValue(diagnostic.gamma_angles_deg, diagnostic.intensities_cd_per_klm[left], gamma);
    const rightValue = pchipValue(diagnostic.gamma_angles_deg, diagnostic.intensities_cd_per_klm[right], gamma);
    return Math.max(0, (1 - fraction) * leftValue + fraction * rightValue);
  };
  return {
    ...diagnostic,
    c_angles_deg: cAngles,
    gamma_angles_deg: gammaAngles,
    intensities_cd_per_klm: cAngles.map(c => gammaAngles.map(gamma => sample(c, gamma))),
  };
}

function LdtSurface({ diagnostic }: { diagnostic: LdtDiagnostic }) {
  const surfaceDiagnostic = useMemo(() => smoothLdtDiagnostic(diagnostic), [diagnostic]);
  const [azimuth, setAzimuth] = useState(28);
  const [elevation, setElevation] = useState(24);
  const [scale, setScale] = useState(1);
  const pointerRef = useRef<{ button: number; x: number; y: number } | null>(null);
  const cAngles = surfaceDiagnostic.c_angles_deg;
  const gammas = surfaceDiagnostic.gamma_angles_deg;
  const max = Math.max(surfaceDiagnostic.max_intensity_cd_per_klm, 1);
  const originY = 54;
  const project = (x: number, y: number, z: number) => {
    const yaw = azimuth * Math.PI / 180;
    const pitch = elevation * Math.PI / 180;
    const yawX = x * Math.cos(yaw) - y * Math.sin(yaw);
    const yawY = x * Math.sin(yaw) + y * Math.cos(yaw);
    const screenY = (yawY * Math.sin(pitch) + z * Math.cos(pitch)) * scale;
    const depth = yawY * Math.cos(pitch) - z * Math.sin(pitch);
    return { point: `${300 + yawX * 190 * scale},${originY + screenY * 170}`, depth };
  };
  const spherical = (c: number, gamma: number, value: number) => {
    const cRadians = c * Math.PI / 180;
    const gammaRadians = gamma * Math.PI / 180;
    const radius = Math.sqrt(Math.max(value, 0) / max) * 1.08;
    return [
      radius * Math.sin(gammaRadians) * Math.cos(cRadians),
      radius * Math.sin(gammaRadians) * Math.sin(cRadians),
      radius * Math.cos(gammaRadians),
    ] as const;
  };
  const cells: { key: string; points: string; fill: string; opacity: number; depth: number }[] = [];
  for (let c = 0; c < cAngles.length; c += 1) for (let g = 0; g < gammas.length - 1; g += 1) {
    const nextC = (c + 1) % cAngles.length;
    const nextAngle = nextC === 0 ? cAngles[0] + 360 : cAngles[nextC];
    const values = [surfaceDiagnostic.intensities_cd_per_klm[c][g], surfaceDiagnostic.intensities_cd_per_klm[nextC][g], surfaceDiagnostic.intensities_cd_per_klm[nextC][g + 1], surfaceDiagnostic.intensities_cd_per_klm[c][g + 1]];
    const average = values.reduce((sum, value) => sum + value, 0) / values.length;
    const vertices = [
      project(...spherical(cAngles[c], gammas[g], values[0])),
      project(...spherical(nextAngle, gammas[g], values[1])),
      project(...spherical(nextAngle, gammas[g + 1], values[2])),
      project(...spherical(cAngles[c], gammas[g + 1], values[3])),
    ];
    const hue = 145 - Math.sqrt(average / max) * 145;
    const opacity = .42 + Math.min(average / max, 1) * .45;
    cells.push({
      key: `${c}-${g}`,
      points: vertices.map(vertex => vertex.point).join(' '),
      fill: `hsl(${hue} 66% ${25 + (average / max) * 42}%)`,
      opacity,
      depth: vertices.reduce((sum, vertex) => sum + vertex.depth, 0) / vertices.length,
    });
  }
  const handlePointerDown = (event: PointerEvent<SVGSVGElement>) => {
    if (event.button !== 0 && event.button !== 2) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    pointerRef.current = { button: event.button, x: event.clientX, y: event.clientY };
  };
  const handlePointerMove = (event: PointerEvent<SVGSVGElement>) => {
    const previous = pointerRef.current;
    if (!previous) return;
    const dx = event.clientX - previous.x;
    const dy = event.clientY - previous.y;
    if (previous.button === 2) {
      setAzimuth(value => Math.max(-180, Math.min(180, value + dx * .55)));
      setElevation(value => Math.max(-80, Math.min(80, value + dy * .45)));
    } else {
      setScale(value => Math.max(.45, Math.min(1.9, value - dy * .008)));
    }
    pointerRef.current = { ...previous, x: event.clientX, y: event.clientY };
  };
  const stopPointer = (event: PointerEvent<SVGSVGElement>) => {
    pointerRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  return <div className="ldt-surface-wrap"><div className="ldt-surface-head"><span>SÓLIDO FOTOMÉTRICO / cd/klm</span><small>radio = intensidad normalizada</small></div><svg className="ldt-surface interactive" viewBox="0 0 600 270" role="img" aria-label={`Sólido fotométrico 3D del LDT ${diagnostic.name}`} onContextMenu={event => event.preventDefault()} onPointerDown={handlePointerDown} onPointerMove={handlePointerMove} onPointerUp={stopPointer} onPointerCancel={stopPointer}><rect width="600" height="270" fill="#153b34" /><g opacity=".35"><ellipse cx="300" cy={originY} rx="206" ry="38" fill="none" stroke="#aac4b0" /><ellipse cx="300" cy={originY} rx="105" ry="20" fill="none" stroke="#aac4b0" /><path d={`M94 ${originY}H506M300 20V250`} stroke="#aac4b0" /></g><g>{cells.sort((a, b) => a.depth - b.depth).map(cell => <polygon key={cell.key} points={cell.points} fill={cell.fill} fillOpacity={cell.opacity} stroke="rgba(221,239,218,.45)" strokeWidth=".5" />)}</g><path d={`M300 ${originY}L500 ${originY}M300 ${originY}L300 20`} stroke="#b9e77a" strokeWidth="1" opacity=".75" /><text x="508" y={originY + 6} fill="#b9e77a" fontSize="10" fontFamily="DM Mono, monospace">C</text><text x="305" y="265" fill="#b9e77a" fontSize="10" fontFamily="DM Mono, monospace">gamma 0°</text><circle cx="300" cy={originY} r="3" fill="#ef7348" /></svg><div className="ldt-controls ldt-mouse-help"><span>BOTÓN DERECHO + ARRASTRAR · GIRAR</span><span>BOTÓN IZQUIERDO + ARRASTRAR · TAMAÑO</span><b>{Math.round(scale * 100)} %</b></div></div>;
}

function LdtGridTable({ diagnostic }: { diagnostic: LdtDiagnostic }) {
  const mismatchFor = (angle: number) => diagnostic.pairs.find(pair => Math.abs(pair.c_deg - angle) < .01 || Math.abs(pair.mirror_c_deg - angle) < .01)?.symmetric === false;
  return <div className="ldt-table-wrap"><div className="ldt-table-caption"><span>TABLA INTENSIDAD / C × GAMMA</span><small>rojo = par no simétrico</small></div><div className="ldt-table-scroll"><table className="ldt-table"><thead><tr><th>C / gamma</th>{diagnostic.gamma_angles_deg.map(gamma => <th key={gamma}>{gamma.toFixed(0)}°</th>)}</tr></thead><tbody>{diagnostic.c_angles_deg.map((angle, index) => <tr className={mismatchFor(angle) ? 'mismatch' : ''} key={angle}><th>{angle.toFixed(2)}°</th>{diagnostic.intensities_cd_per_klm[index].map((value, gammaIndex) => <td key={`${angle}-${gammaIndex}`}>{value.toFixed(0)}</td>)}</tr>)}</tbody></table></div></div>;
}

export default App;
