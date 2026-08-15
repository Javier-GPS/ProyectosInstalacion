import { ChangeEvent, FormEvent, PointerEvent, useMemo, useRef, useState } from 'react';

const API_URL = (import.meta.env.VITE_OPTIMIZER_API_URL || 'http://127.0.0.1:8760').replace(/\/$/, '');
const GROUP_ANGLES = [11.25, 33.75, 56.25, 78.75, 101.25, 123.75, 146.25, 168.75];
const CURRENT_OPTIONS = Array.from({ length: 41 }, (_, index) => index * 50);
const CCT_OPTIONS = [2200, 2700, 3000, 3500, 4000, 5000, 5700, 6500];

type FilePayload = { name: string; base64: string } | null;
type OperatingGroup = { current_ma: number; group_flux_lm: number; vf_v: number; group_power_w: number; tj_c: number; kt: number };
type OperatingPoint = { groups: OperatingGroup[]; total_flux_lm: number; total_driver_power_w: number; solder_temperature_c: number; converged: boolean; power_limit_ok: boolean };
type Metrics = { lavg_cd_m2: number; uo: number; ul: number; ti_pct: number; rei: number; compliant: boolean; criteria: Record<string, boolean>; warnings: string[]; power_limit_ok: boolean };
type GroupPhotometricProfile = { azimuth_deg: number; flux_lm: number; normalized: number[]; max_intensity_cd: number };
type PhotometricProfile = { gamma_deg: number; c_angles_deg: number[]; normalized: number[]; max_intensity_cd: number; group_angles_deg: number[]; groups: GroupPhotometricProfile[] };
type LaneVisualGrid = { lane_index: number; observer_y_m: number; luminance_cd_m2: number[][] };
type LaneProfile = { lane_index: number; observer_y_m: number; luminance_cd_m2: number[] };
type VisualGrid = { xs_m: number[]; ys_m: number[]; illuminance_lx: number[][]; luminance_cd_m2: number[][]; lane_grids?: LaneVisualGrid[]; lane_profiles?: LaneProfile[]; normative_profile?: LaneProfile; worst_lane_index?: number; lane_centres_m?: number[]; lane_widths_m?: number[]; observer_x_m?: number; observer_distance_m?: number };
type MapMetric = 'luminance' | 'illuminance';
type LdtPair = { c_deg: number; mirror_c_deg: number; max_difference_pct: number; worst_gamma_deg: number; symmetric: boolean };
type LdtDiagnostic = { name: string; company: string; flux_lm: number; power_w: number; c_angles_deg: number[]; gamma_angles_deg: number[]; intensities_cd_per_klm: number[][]; max_intensity_cd_per_klm: number; symmetry_tolerance_pct: number; pairs: LdtPair[]; symmetric: boolean };
type Result = { feasible?: boolean; currents_ma: number[]; operating_point: OperatingPoint; metrics?: Metrics; photometric_profile?: PhotometricProfile; visual_grid?: VisualGrid; group_ldt?: LdtDiagnostic; luminaire_ldt?: LdtDiagnostic; message?: string };

const encodeFile = (file: File): Promise<FilePayload> => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve({ name: file.name, base64: String(reader.result).split(',')[1] || '' });
  reader.onerror = () => reject(reader.error || new Error(`No se pudo leer ${file.name}`));
  reader.readAsDataURL(file);
});

function NumberField({ label, value, onChange, suffix, min, max, step }: { label: string; value: number; onChange: (value: number) => void; suffix?: string; min?: number; max?: number; step?: number }) {
  return <label className="field"><span>{label}</span><div className="number-input"><input type="number" value={value} min={min} max={max} step={step} onChange={event => onChange(Number(event.target.value))} /><small>{suffix}</small></div></label>;
}

function FileDrop({ label, hint, file, accept, onFile }: { label: string; hint: string; file: FilePayload; accept: string; onFile: (file: FilePayload) => void }) {
  const handle = async (event: ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0];
    if (selected) onFile(await encodeFile(selected));
  };
  return <label className={`file-drop ${file ? 'loaded' : ''}`}>
    <input type="file" accept={accept} onChange={handle} />
    <span className="file-glyph">{file ? '✓' : '+'}</span>
    <span><strong>{file ? file.name : label}</strong><small>{file ? 'Archivo cargado' : hint}</small></span>
  </label>;
}

function App() {
  const [ldt, setLdt] = useState<FilePayload>(null);
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
  const requestBody = () => {
    if (!ldt || !rtable) throw new Error('Carga el LDT del grupo y una tabla R/C2 antes de calcular.');
    return {
      group_ldt_base64: ldt.base64,
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
      optimization_mode: 'independent',
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
           <div className="file-grid"><FileDrop label="LDT del grupo" hint="3 LED + lente / EULUMDAT" file={ldt} accept=".ldt" onFile={handleLdt} /></div>
           {groupLdtDiagnostic && <LdtDiagnostics title="LDT DEL GRUPO / 3 LED + LENTE" diagnostic={groupLdtDiagnostic} />}
          <div className="field-grid three"><label className="field"><span>CCT</span><select value={cct} onChange={event => setCct(Number(event.target.value))}>{CCT_OPTIONS.map(value => <option key={value} value={value}>{value} K</option>)}</select></label><label className="field"><span>CRI</span><select value={cri} onChange={event => setCri(Number(event.target.value))}><option value={70}>70</option><option value={80}>80</option><option value={90}>90</option></select></label></div>
          <div className="field-grid three"><NumberField label="Ambiente" value={ambient} onChange={setAmbient} suffix="°C" min={-40} max={80} /><NumberField label="Coef. Tsp" value={tsCoefficient} onChange={setTsCoefficient} suffix="°C/W" step={0.01} min={0} /><NumberField label="Driver" value={driverEfficiency} onChange={setDriverEfficiency} suffix="η" step={0.01} min={0.1} max={1} /></div>
          <p className="note"><span>i</span> El flujo del LDT es el anclaje fotométrico del grupo. La temperatura y la corriente modifican el flujo mediante el modelo iterativo HL2X.</p>
        </section>}
        {activePanel === 'road' && <section className="panel-content">
          <div className="section-heading"><div><p className="eyebrow">ESCENARIO VIAL</p><h2>Geometría de cálculo</h2></div><span className="tag">EN 13201 / M</span></div>
          <div className="field-grid three"><NumberField label="Altura fotométrica" value={height} onChange={setHeight} suffix="m" step={0.05} min={0.5} max={5} /><NumberField label="Interdistancia" value={spacing} onChange={setSpacing} suffix="m" step={0.5} min={1} max={40} /><NumberField label="Anchura de carril" value={width} onChange={setWidth} suffix="m" step={0.1} min={2} max={8} /></div>
           <div className="field-grid three"><NumberField label="Offset desde el canto" value={edgeOffset} onChange={setEdgeOffset} suffix="m" step={0.1} min={0} max={5} /><NumberField label="Tilt LDT luminaria" value={tilt} onChange={setTilt} suffix="°" step={0.5} min={-10} max={10} /></div>
          <div className="file-grid"><FileDrop label="Tabla de reflexión" hint="R1, R2, R3, R4 o C2" file={rtable} accept=".rtb,.txt" onFile={setRtable} /></div>
          <div className="field-grid three"><label className="field"><span>Tabla activa</span><select value={rtableName} onChange={event => setRtableName(event.target.value)}><option value="C2">C2 rasante</option><option value="R1">R1</option><option value="R2">R2</option><option value="R3">R3</option><option value="R4">R4</option></select></label><label className="field"><span>Carriles</span><select value={lanes} onChange={event => setLanes(Number(event.target.value))}>{[1, 2, 3, 4].map(value => <option key={value} value={value}>{value}</option>)}</select></label><label className="field"><span>Disposición</span><select value={arrangement} onChange={event => setArrangement(event.target.value)}><option value="unilateral">Unilateral</option><option value="bilateral_paired">Bilateral pareada</option><option value="bilateral_staggered">Bilateral tresbolillo</option></select></label></div>
          <div className="field-grid three"><label className="field"><span>Clase luminotécnica</span><select value={lightingClass} onChange={event => setLightingClass(event.target.value)}>{['M1', 'M2', 'M3', 'M4', 'M5', 'M6'].map(value => <option key={value}>{value}</option>)}</select></label></div>
          <RoadAnimation width={width * lanes} height={height} spacing={spacing} edgeOffset={edgeOffset} arrangement={arrangement} />
          <p className="note"><span>i</span> Las luminarias opuestas se giran 180° y utilizan el mismo perfil de ocho corrientes.</p>
        </section>}
        {activePanel === 'groups' && <section className="panel-content">
          <div className="section-heading"><div><p className="eyebrow">PERFIL DE CONTROL</p><h2>Corriente por grupo</h2></div><span className="tag">0 — 2000 mA</span></div>
          <div className="group-list">{GROUP_ANGLES.map((angle, index) => <div className="group-row" key={angle}><div className="group-index">G{String(index + 1).padStart(2, '0')}</div><div className="group-angle"><strong>{angle.toFixed(2)}°</strong><small>azimut C</small></div><input className="range" type="range" min={0} max={2000} step={50} value={currents[index]} onChange={event => updateCurrent(index, Number(event.target.value))} /><select className="current-select" value={currents[index]} onChange={event => updateCurrent(index, Number(event.target.value))}>{CURRENT_OPTIONS.map(value => <option key={value} value={value}>{value} mA</option>)}</select><span className="group-flow">{result ? `${format(result.operating_point.groups[index]?.group_flux_lm, 0)} lm` : '—'}</span></div>)}</div>
          <button className="equalize" type="button" onClick={() => setCurrents(Array(8).fill(currents[0]))}>Igualar los ocho grupos</button>
        </section>}
        {error && <div className="error-banner" role="alert">{error}</div>}
        <div className="action-bar"><button className="secondary-button" type="button" onClick={() => run('/api/road/calculate')} disabled={busy}>{busy ? 'Calculando…' : 'Evaluar perfil'}</button><button className="primary-button" type="button" onClick={() => run('/api/optimize')} disabled={busy}>{busy ? 'Optimizando…' : 'Optimizar corrientes'} <span>→</span></button></div>
      </form>
    </div>
    <section className="results-section"><div className="results-heading"><div><p className="eyebrow">LIVE OUTPUT / {lightingClass}</p><h2>Lectura de la solución</h2></div><span className={`result-state ${result?.metrics?.compliant ? 'good' : result ? 'warn' : ''}`}>{result?.metrics?.compliant ? 'CONFORME' : result ? 'REVISAR' : 'SIN CÁLCULO'}</span></div>
      <div className="metric-grid"><Metric label="Flujo total" value={totalFlux ? `${format(totalFlux, 0)} lm` : '—'} /><Metric label="Potencia entrada" value={totalPower ? `${format(totalPower, 1)} W` : '—'} /><Metric label="Lavg" value={result?.metrics ? `${format(result.metrics.lavg_cd_m2, 2)} cd/m²` : '—'} /><Metric label="Uo" value={result?.metrics ? format(result.metrics.uo, 2) : '—'} /><Metric label="Ul" value={result?.metrics ? format(result.metrics.ul, 2) : '—'} /></div>
        <div className="visual-card"><div className="card-title"><span>MAPA PUNTO A PUNTO</span><small>isocurvas / luminancia cd/m²</small></div>{result?.visual_grid ? <LuminanceMap grid={result.visual_grid} luminaireLdt={result.luminaire_ldt} carriagewayWidth={width * lanes} spacing={spacing} edgeOffset={edgeOffset} arrangement={arrangement} selectedLane={selectedLane} onLaneChange={setSelectedLane} /> : <div className="empty-result">Ejecuta una evaluación para visualizar la distribución sobre la calzada.</div>}</div>
        {result?.visual_grid?.normative_profile && <NormativeGraph xs={result.visual_grid.xs_m} profiles={result.visual_grid.lane_profiles || []} worstLane={result.visual_grid.worst_lane_index ?? result.visual_grid.normative_profile.lane_index} selectedLane={selectedLane} onLaneChange={setSelectedLane} />}
       {result?.group_ldt && <LdtDiagnostics title="DIAGNÓSTICO FOTOMÉTRICO / GRUPO" diagnostic={result.group_ldt} />}
       {result?.luminaire_ldt && <LdtDiagnostics title="DIAGNÓSTICO FOTOMÉTRICO / LUMINARIA CALCULADA" diagnostic={result.luminaire_ldt} />}
      <div className="group-results"><div className="card-title"><span>RESULTADO POR GRUPO</span><small>perfil aplicado en todas las luminarias</small></div><div className="group-results-grid">{GROUP_ANGLES.map((angle, index) => { const group = result?.operating_point.groups[index]; return <div className="group-result" key={angle}><strong>G{index + 1}</strong><span>{angle.toFixed(2)}° C</span><b>{result ? `${format(result.currents_ma[index], 0)} mA` : '—'}</b><small>{group ? `${format(group.group_flux_lm, 0)} lm · ${format(group.group_power_w, 1)} W` : 'sin cálculo'}</small></div>; })}</div></div>
       <div className="result-lower"><div className="profile-card"><div className="card-title"><span>PERFIL AZIMUTAL ACTIVO</span><label className="gamma-picker">gamma <select value={displayGamma} onChange={event => setDisplayGamma(Number(event.target.value))}><option value={0}>0°</option><option value={15}>15°</option><option value={30}>30°</option><option value={45}>45°</option><option value={60}>60°</option><option value={75}>75°</option><option value={90}>90°</option></select></label></div><div className="polar"><div className="polar-ring ring-1" /><div className="polar-ring ring-2" /><div className="polar-axis axis-x" /><div className="polar-axis axis-y" />{groupPolarCurves.map((points, index) => <svg className="polar-curve group-curve" viewBox="0 0 240 240" key={`group-curve-${index}`}><polyline points={points} /></svg>)}{polarCurve && <svg className="polar-curve total-curve" viewBox="0 0 240 240" aria-label={`Fotometría a gamma ${displayGamma} grados`}><polyline points={polarCurve} /></svg>}{GROUP_ANGLES.map((angle, index) => <span key={angle} className="polar-ray" style={{ transform: `rotate(${angle - 90}deg)`, height: result ? `${groupFluxes[index] / maxGroupFlux * 72}%` : '0%' }}><i /></span>)}<div className="polar-center">8<span>G</span></div></div><div className="polar-legend"><span className="photometry-key">curva gruesa: suma</span><span>curvas finas: grupos relativos</span></div>{polarProfile && <p className="profile-readout">Imax {format(polarProfile.max_intensity_cd, 0)} cd · gamma {polarProfile.gamma_deg.toFixed(0)}° · máximos orientados por grupo</p>}</div><div className="criteria-card"><div className="card-title"><span>CRITERIOS EN 13201</span><small>{rtableName} / {cct} K / CRI {cri}</small></div>{result?.metrics ? Object.entries(result.metrics.criteria).map(([name, passed]) => <div className="criterion" key={name}><span>{name}</span><strong className={passed ? 'pass' : 'fail'}>{passed ? 'OK' : 'NO'}</strong></div>) : <div className="empty-result">Ejecuta una evaluación para ver el cumplimiento de la clase {lightingClass}.</div>}{result?.metrics?.warnings.map(warning => <p className="warning" key={warning}>! {warning}</p>)}</div></div>
    </section>
    <footer><span>SALVI LIGHTING / ENGINEERING TOOLS</span><span>HL2X 3535 · PROFILE 8×3 SERIES · {API_URL}</span></footer>
  </main>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div>; }

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

function LuminanceMap(props: { grid: VisualGrid; luminaireLdt?: LdtDiagnostic; carriagewayWidth: number; spacing: number; edgeOffset: number; arrangement: string; selectedLane: number; onLaneChange: (lane: number) => void }) {
  const [metric, setMetric] = useState<MapMetric>('luminance');
  const laneCount = props.grid.lane_grids?.length || 1;
  return <div className="luminance-map-shell"><div className="map-toolbar"><label><span>Magnitud</span><select value={metric} onChange={event => setMetric(event.target.value as MapMetric)}><option value="luminance">Luminancia / cd/m²</option><option value="illuminance">Iluminancia / lux</option></select></label>{laneCount > 1 && <label><span>Carril del observador</span><select value={Math.min(props.selectedLane, laneCount - 1)} onChange={event => props.onLaneChange(Number(event.target.value))}>{Array.from({ length: laneCount }, (_, index) => <option key={index} value={index}>Carril {index + 1}</option>)}</select></label>}</div><LuminanceMapSvg {...props} metric={metric} /> </div>;
}

function LuminanceMapSvg({ grid, luminaireLdt, carriagewayWidth, spacing: interdistance, edgeOffset, arrangement, selectedLane, metric }: { grid: VisualGrid; luminaireLdt?: LdtDiagnostic; carriagewayWidth: number; spacing: number; edgeOffset: number; arrangement: string; selectedLane: number; metric: MapMetric }) {
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
   const ldtCells = showLdt && luminaireLdt ? luminairePositions.map((luminaire, index) => <polygon key={`ldt-azimuth-${index}`} className="map-ldt-shape" points={ldtShape(luminaire)} />) : [];
  const ldtVisualScale = .12;
  return <div className="luminance-map"><div className="heatmap-labels"><span>L / cd/m²</span><span>rango {minimum.toFixed(2)} — {maximum.toFixed(2)} cd/m²</span></div><label className="ldt-map-toggle"><input type="checkbox" checked={showLdt} onChange={event => setShowLdt(event.target.checked)} disabled={!luminaireLdt} /> Mostrar vista cenital del LDT completo <small>(escala visual ×{ldtVisualScale.toFixed(2)})</small></label><svg className="luminance-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Mapa de luminancia con isocurvas y luminarias"><rect width={width} height={height} fill="#eef3ec" />{surface}{contourPaths}<rect x={xPosition(0)} y={yPosition(0)} width={xPosition(spacing) - xPosition(0)} height={yPosition(carriagewayWidth) - yPosition(0)} fill="none" stroke="#173e36" strokeWidth="1.5" /><path d={`M${left} ${top + plotHeight}H${left + plotWidth}M${left} ${top}V${top + plotHeight}`} stroke="#173e36" strokeWidth="1" /><text x={left + plotWidth - 8} y={top + plotHeight + 24} textAnchor="end" fill="#52685a" fontSize="10">x / longitudinal</text><text x={left - 8} y={top + 10} textAnchor="end" fill="#52685a" fontSize="10">y / transversal</text>{values.flatMap((row, x) => row.map((value, y) => { const u = xCount > 1 ? (grid.xs_m[x] - mapMinX) / (mapMaxX - mapMinX) : .5; const v = yCount > 1 ? (grid.ys_m[y] - mapMinY) / (mapMaxY - mapMinY) : .5; return <g key={`measurement-${x}-${y}`}><circle cx={px(u)} cy={py(v)} r="3.2" fill="#fff" stroke="#173e36" strokeWidth="1" /><text x={px(u) + 5} y={py(v) - 5} fill="#173e36" fontSize="9" fontFamily="DM Mono, monospace" paintOrder="stroke" stroke="#eef3ec" strokeWidth="3">{value.toFixed(2)}</text></g>; }))}{ldtCells}{luminairePositions.map((luminaire, index) => <g key={`luminaire-${index}`} className="map-luminaire"><line x1={xPosition(luminaire.x)} y1={yPosition(luminaire.y)} x2={xPosition(luminaire.x)} y2={yPosition(luminaire.y < 0 ? 0 : carriagewayWidth)} /><circle cx={xPosition(luminaire.x)} cy={yPosition(luminaire.y)} r="7" /><text x={xPosition(luminaire.x) + 10} y={yPosition(luminaire.y) + 4}>{luminaire.label}</text></g>)}</svg><div className="heatmap-caption"><span>puntos blancos = mediciones originales</span><span>cenital LDT completo · escala visual de orientación · disposición {arrangement}</span></div></div>;
}

function LdtDiagnostics({ title, diagnostic }: { title: string; diagnostic: LdtDiagnostic }) {
  return <section className="ldt-diagnostic">
    <div className="card-title"><span>{title}</span><small>{diagnostic.name} · {diagnostic.c_angles_deg.length} C × {diagnostic.gamma_angles_deg.length} gamma</small></div>
    <div className="ldt-diagnostic-grid">
      <LdtSurface diagnostic={diagnostic} />
      <div className="ldt-pair-panel">
        <div className={`symmetry-banner ${diagnostic.symmetric ? 'good' : 'bad'}`}><b>{diagnostic.symmetric ? 'SIMÉTRICO' : 'ASIMÉTRICO'}</b><span>tolerancia ±{diagnostic.symmetry_tolerance_pct.toFixed(1)} %</span></div>
        <div className="ldt-pair-list">{diagnostic.pairs.map(pair => <div className={`ldt-pair ${pair.symmetric ? '' : 'mismatch'}`} key={`${pair.c_deg}-${pair.mirror_c_deg}`}><span>C {pair.c_deg.toFixed(2)}° ↔ {pair.mirror_c_deg.toFixed(2)}°</span><b>{pair.max_difference_pct.toFixed(1)} %</b><small>gamma {pair.worst_gamma_deg.toFixed(0)}° · {pair.symmetric ? 'OK' : 'NO SIMÉTRICO'}</small></div>)}</div>
      </div>
    </div>
    <LdtGridTable diagnostic={diagnostic} />
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
