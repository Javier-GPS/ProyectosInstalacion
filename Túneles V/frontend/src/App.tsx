import { useEffect, useState } from 'react';
import type { ChangeEvent, FormEvent, ReactNode } from 'react';
import { calculateControl, calculateLuminaires, calculateTunnel, createProject, deleteProject, getProject, listProjects, updateProject, validateTunnel } from './api';
import type { ProjectPayload, ProjectRecord, TunnelConfig } from './types';
import { I18nProvider, useI18n } from './i18n';

const today = () => new Date().toISOString().slice(0, 10);
const orientations = ['S', 'NE', 'E', 'SE', 'SW', 'W', 'NW', 'N'];
const oppositeOrientation: Record<string, string> = { N: 'S', NE: 'SW', E: 'W', SE: 'NW', S: 'N', SW: 'NE', W: 'E', NW: 'SE' };

const automaticFriction = (speedKmh: number) => {
  if (speedKmh <= 50) return 0.50;
  if (speedKmh <= 70) return 0.45;
  if (speedKmh <= 90) return 0.40;
  if (speedKmh <= 110) return 0.35;
  return 0.30;
};

const defaultTunnelConfig: TunnelConfig = {
  project_name: 'Proyecto Túnel', tube_id: 'T1', length_m: 300, speed_kmh: 80,
  gradient_pct: 0, curvature_radius_m: '', traffic_direction: 'one_way',
  mu_friction: '', t_reaction: 2.5, width_m: 10.5, height_m: 5.5,
  num_lanes: 2, lane_width_m: 3.5, shoulder_left_m: 0, shoulder_right_m: 0,
  sidewalk_left_m: 0, sidewalk_right_m: 0, include_shoulders_in_luminance_grid: false,
  portal_orientation: 'S', portal_mode: 'manual', portal_lane_ref_m: 3.5,
  tunnel_shape: 'horseshoe', H_pared_m: 3, road_surface: 'medium_asphalt', calc_mode: 'direct',
  environment_type: 'open_country_flat', sky_condition: 'clear', daylight_penetration: 'poor',
  wall_reflectance: 0.4, rho_wall: 0.4, rho_ceiling: 0.25, wall_luminance_height_m: 2,
  wall_ratio_override: '',
  exit_visible: false, illuminated_road: false, traffic_veh_h: 500,
  imd: 500, k_peak: 0.10, has_pedestrians: false, interior_luminance_override: '',
  l20_method: 'model', lth_method: 'k_factor',
  lth_standard: 'oc36_2015', tunnel_class: 'auto', l20_override: '', l20_b_override: '',
  lth_override: '', lth_b_override: '', lseq_override: '', lseq_b_override: '',
  qc_override: 0.1, contrast_observation: 0.04, profile_stepped: false, n_steps: 4,
  n_transition_groups: 2,
  stopping_distance_override_m: '', stopping_distance_b_override_m: '',
  threshold_length_override_m: '', threshold_length_b_override_m: '',
  transition_end_override_m: '', transition_end_b_override_m: '',
  exit_length_override_m: '', exit_luminance_ratio_override: 100,
  k_lth_override: '', k_lth_b_override: '',
  dp_override: '', dp_b_override: '', ta_design_c: 20,
  annual_operation_hours: 8760, night_operation_hours: 4300,
  night_reduced_share_pct: 30, energy_tariff_eur_kwh: 0.15,
  night_normal_luminance_cd_m2: '', night_reduced_luminance_cd_m2: '',
  control_protocol: 'DALI', sensor_type: 'luminancemeter_L20', sample_interval_min: 10,
  ramp_time_s: 60, dim_min_pct: 20, dim_max_pct: 100, driver_min_dim_pct: 0.1,
  control_topology: 'smartec_wirepas', control_architecture: 'permanent_base_plus_portal_reinforcement', wirepas_nodes_per_gateway: 200,
  dali_max_addresses_per_line: 64, dali_group_span_m: 60, dali_cabinet_position_m: 0,
  report_video_url: '', report_video_title: '', report_version: 'v2',
  manual_luminaire_overrides: {}, tilt_overrides: {}, tandem_overrides: {},
  scene_current_overrides: {},
  lum_config: {
    I_max_mA: 750, I_min_pct: 30, cct: '4000K', optic: 'auto', arrangement: 'bilateral_sym',
    mounting_height_m: 4.5, wall_offset_m: 0.3, axis_offset_m: 0.3, maintenance_factor: 0.7,
    road_surface: 'medium_asphalt', U0_obj: 0.4, Ul_obj: 0.6, tilt_max: 20, d_fixed: '', d_min: 1,
    optimization_goal: 'min_luminaires', max_luminaire_increase_pct: 15,
    max_base_spacing_reduction_pct: 20, spacing_quantum_m: 0.5,
    constructive_min_separation_m: 0.5, transition_spacing_step_m: 2,
    luminance_margin_pct: 4, scene_excess_ratio_pct: 4,
    auto_physical_reoptimization: true, scene_reoptimization_max_spacing_reduction_pct: 35,
    scene_reoptimization_max_attempts: 3, daylight_contribution_enabled: false,
    daylight_portal_a: true, daylight_portal_b: true, daylight_penetration_length_m: 60,
    daylight_mouth_contribution_pct: 10, daylight_decay_exponent: 1,
  },
};

const blankProject = (): ProjectPayload => ({
  project_name: '', client: '', location: '', designer: '', study_date: today(),
  reference: '', calculation_type: 'Iluminación de túneles',
  standard: 'CIE 88:2004 / CIE 140', notes: '', status: 'draft',
});

function App() {
  return <I18nProvider><AppContent /></I18nProvider>;
}

function AppContent() {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => { const onPopState = () => setPath(window.location.pathname); window.addEventListener('popstate', onPopState); return () => window.removeEventListener('popstate', onPopState); }, []);
  const route = path.match(/^\/projects\/(\d+)$/);
  return route ? <ProjectEditor projectId={Number(route[1])} /> : <ProjectsPage />;
}

function Header({ onProjects }: { onProjects?: () => void }) {
  const [panel, setPanel] = useState<'ai' | 'help' | null>(null);
  const { language, setLanguage, t } = useI18n();
  const [question, setQuestion] = useState(''); const [answer, setAnswer] = useState(''); const [asking, setAsking] = useState(false);
  const ask = async () => { if (!question.trim()) return; setAsking(true); setAnswer(''); try { const response = await fetch('/api/tunnel/ai-assistant', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: question.trim() }) }); const data = await response.json(); setAnswer(data.answer || data.error || t('ai.error')); } catch { setAnswer(t('ai.connectionError')); } finally { setAsking(false); } };
  useEffect(() => { document.title = `${t('nav.tunnels')} · SALVI Studio`; }, [language, t]);
  const chooseLanguage = (next: string) => { setLanguage(next as Parameters<typeof setLanguage>[0]); };
  return <header className="topbar">
    <button className="brand" onClick={onProjects} type="button" aria-label={t('aria.goProjects')}>
      <span className="brand-mark" aria-hidden="true"><span /></span><span><strong>SALVI Studio</strong><small>{t('app.subtitle')}</small></span>
    </button>
    <nav className="topnav"><span>{t('nav.lighting')}</span><span>{t('nav.tunnels')}</span><span>{t('app.standards')}</span><div className="language-picker" aria-label={t('aria.selectLanguage')}>{['ES', 'EN', 'FR', 'CA', 'IT'].map(lang => <button key={lang} type="button" aria-pressed={lang === language} className={lang === language ? 'language active' : 'language'} onClick={() => chooseLanguage(lang)}>{lang}</button>)}</div><span className="language-status">{language}</span><button type="button" className="header-action" onClick={() => setPanel('ai')}>{t('nav.ai')}</button><button type="button" className="header-action" onClick={() => setPanel('help')}>{t('nav.help')}</button></nav>
    {panel && <div className="header-popover"><strong>{panel === 'ai' ? t('ai.title') : t('help.title')}</strong><button type="button" onClick={() => setPanel(null)} aria-label={t('aria.close')}>×</button>{panel === 'ai' ? <><p>{t('ai.description')}</p><div className="ai-question"><input value={question} onChange={event => setQuestion(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') void ask(); }} placeholder={t('ai.placeholder')} /><button type="button" className="primary" onClick={() => void ask()} disabled={asking}>{asking ? t('ai.asking') : t('ai.ask')}</button></div>{answer && <div className="ai-answer">{answer}</div>}</> : <p>{t('help.description')}</p>}</div>}
  </header>;
}

function ProjectsPage() {
  const { t } = useI18n();
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [modal, setModal] = useState(false);
  const [editingProject, setEditingProject] = useState<ProjectRecord | null>(null);

  const load = async () => {
    setLoading(true); setError('');
    try { setProjects(await listProjects()); }
    catch (err) { setError(err instanceof Error ? err.message : t('editor.noProjects')); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  const open = (id: number) => { window.history.pushState({}, '', `/projects/${id}`); window.dispatchEvent(new PopStateEvent('popstate')); };
  const remove = async (project: ProjectRecord) => {
    if (!window.confirm(t('project.confirmDelete', { name: project.project_name }))) return;
    try { await deleteProject(project.id); setProjects(current => current.filter(item => item.id !== project.id)); }
    catch (err) { setError(err instanceof Error ? err.message : t('editor.projectDeleteFailed')); }
  };
  const startCreate = () => { setEditingProject(null); setModal(true); };
  const startEdit = (project: ProjectRecord) => { setEditingProject(project); setModal(true); };
  const saved = (savedProject: ProjectRecord) => {
    const wasEditing = Boolean(editingProject);
    setModal(false); setEditingProject(null);
    if (wasEditing) setProjects(current => current.map(project => project.id === savedProject.id ? savedProject : project));
    else open(savedProject.id);
  };

  return <div className="app"><Header />
     <main className="page projects-page">
       <div className="page-heading"><div><span className="eyebrow">SALVI TUNNEL ENGINE</span><h1>{t('projects.title')}</h1><p>{t('projects.subtitle')}</p></div><button className="primary" onClick={startCreate}>{t('projects.new')}</button></div>
      {error && <div className="alert error">{error}</div>}
     {loading ? <div className="loading-card">{t('projects.loading')}</div> : projects.length === 0 ? <EmptyState onCreate={startCreate} /> :
        <div className="project-grid"><button className="new-card" onClick={startCreate}><span>＋</span><strong>{t('projects.newCard')}</strong><small>{t('projects.newCardHint')}</small></button>
          {projects.map(project => <ProjectCard key={project.id} project={project} onOpen={() => open(project.id)} onEdit={() => startEdit(project)} onDelete={() => void remove(project)} />)}
        </div>}
    </main>
    {modal && <ProjectModal project={editingProject} onClose={() => { setModal(false); setEditingProject(null); }} onSaved={saved} />}
  </div>;
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  const { t } = useI18n();
  return <section className="empty-state"><div className="empty-icon">⌂</div><h2>{t('projects.emptyTitle')}</h2><p>{t('projects.emptyDescription')}</p><button className="primary" onClick={onCreate}>{t('projects.emptyCta')}</button></section>;
}

function ProjectCard({ project, onOpen, onEdit, onDelete }: { project: ProjectRecord; onOpen: () => void; onEdit: () => void; onDelete: () => void }) {
  const { t, language } = useI18n();
  return <article className="project-card">
    <div className="project-card-body"><button className="card-open" onClick={onOpen}><h2>{project.project_name}</h2><p>{project.location || t('project.locationUnknown')}</p></button>
    <dl><div><dt>{t('project.client')}</dt><dd>{project.client || '—'}</dd></div><div><dt>{t('project.studyDate')}</dt><dd>{formatDate(project.study_date, language)}</dd></div><div><dt>{t('project.lastOpened')}</dt><dd>{formatDate(project.last_opened_at, language)}</dd></div><div><dt>{t('project.standard')}</dt><dd>{project.standard || 'CIE 88:2004 / CIE 140'}</dd></div></dl></div>
    <div className="card-actions"><button className="card-action-open" onClick={onOpen}>{t('project.open')}</button><button className="card-action-icon edit" onClick={onEdit} title={t('project.edit')} aria-label={t('project.edit')}>✎</button><button className="card-action-icon delete" onClick={onDelete} title={t('project.delete')} aria-label={t('project.delete')}>🗑</button></div>
  </article>;
}

function ProjectModal({ project, onClose, onSaved }: { project: ProjectRecord | null; onClose: () => void; onSaved: (project: ProjectRecord) => void }) {
  const { t } = useI18n();
  const [value, setValue] = useState<ProjectPayload>(() => project ? {
    project_name: project.project_name, client: project.client || '', location: project.location || '', designer: project.designer || '', study_date: project.study_date || '', reference: project.reference || '', calculation_type: project.calculation_type || t('placeholder.calculationType'), standard: project.standard || 'CIE 88:2004 / CIE 140', notes: project.notes || '', status: project.status || 'draft', config_json: project.config_json || undefined, result_json: project.result_json || null,
    } : { ...blankProject(), calculation_type: t('placeholder.calculationType') });
  const [saving, setSaving] = useState(false); const [error, setError] = useState('');
  const update = (key: keyof ProjectPayload, next: string) => setValue(current => ({ ...current, [key]: next }));
  const submit = async (event: FormEvent) => {
    event.preventDefault(); if (!value.project_name?.trim()) return;
    setSaving(true); setError('');
     try {
       const payload = project
         ? { ...value, project_name: value.project_name.trim(), config_json: project.config_json || undefined, result_json: project.result_json || null, status: project.status || 'draft' }
         : { ...value, project_name: value.project_name.trim(), config_json: { ...defaultTunnelConfig, project_name: value.project_name.trim() } };
       onSaved(await (project ? updateProject(project.id, payload) : createProject(payload)));
     }
     catch (err) { setError(err instanceof Error ? err.message : t('editor.projectSaveFailed')); }
    finally { setSaving(false); }
  };
  return <ModalShell title={project ? t('modal.editProject') : t('modal.newProject')} onClose={onClose}><form onSubmit={submit}>
    <div className="form-grid"> <TextField label={t('field.projectName')} value={value.project_name || ''} required onChange={v => update('project_name', v)} placeholder={t('placeholder.projectName')} />
      <TextField label={t('field.client')} value={value.client || ''} onChange={v => update('client', v)} placeholder={t('placeholder.client')} />
      <TextField label={t('field.location')} value={value.location || ''} onChange={v => update('location', v)} placeholder={t('placeholder.location')} />
      <TextField label={t('field.designer')} value={value.designer || ''} onChange={v => update('designer', v)} placeholder={t('placeholder.designer')} />
      <TextField label={t('field.studyDate')} type="date" value={value.study_date || ''} onChange={v => update('study_date', v)} />
      <TextField label={t('field.reference')} value={value.reference || ''} onChange={v => update('reference', v)} placeholder={t('placeholder.reference')} />
      <TextField label={t('field.calculationType')} value={value.calculation_type || ''} onChange={v => update('calculation_type', v)} placeholder={t('placeholder.calculationType')} />
      <TextField label={t('field.standard')} value={value.standard || ''} onChange={v => update('standard', v)} placeholder={t('placeholder.standard')} />
      <TextField label={t('field.notes')} value={value.notes || ''} onChange={v => update('notes', v)} placeholder={t('placeholder.notes')} textarea />
    </div>
    {error && <div className="alert error">{error}</div>}<div className="modal-actions"><button type="button" className="secondary" onClick={onClose}>{t('action.cancel')}</button><button className="primary" disabled={saving || !value.project_name?.trim()}>{saving ? t('action.saving') : project ? t('action.saveChanges') : t('action.saveProject')}</button></div>
  </form></ModalShell>;
}

function RoadConfiguration({ config, onChange }: { config: TunnelConfig; onChange: (key: string, value: unknown) => void }) {
  const { t } = useI18n();
  const portalB = oppositeOrientation[String(config.portal_orientation)] || 'N';
  const imd = config.imd === '' || config.imd == null ? 0 : Math.max(0, Number(config.imd) || 0);
  const kPeak = Number(config.k_peak) || 0.10;
  const isTwoWay = String(config.traffic_direction) === 'two_way';
  const speedOptions = [40, 50, 60, 70, 80, 90, 100, 110, 120];
  const selectedSpeed = speedOptions.includes(Number(config.speed_kmh)) ? String(config.speed_kmh) : '80';
  // La IMD publicada por DGT es el total de ambos sentidos. Para un tubo
  // unidireccional se toma la mitad; en uno bidireccional pasa todo el flujo.
  const designTrafficFromImd = imd > 0
    ? Math.round(imd * kPeak * (isTwoWay ? 1 : 0.5))
    : 0;
  return <Panel title={t('panel.roadTitle')} intro={t('panel.roadIntro')}>
    <SectionTitle title={t('section.mainGeometry')} />
    <div className="form-grid compact-grid">
      <TextField label={t('field.tubeId')} value={String(config.tube_id)} onChange={value => onChange('tube_id', value)} />
      <SelectField label={t('field.tunnelShape')} value={String(config.tunnel_shape)} options={[["horseshoe", t('option.horseshoe')], ["rectangular", t('option.rectangular')], ["circular", t('option.circular')]]} onChange={value => onChange('tunnel_shape', value)} />
      <NumberField label={t('field.length')} unit="m" value={config.length_m} min={10} onChange={value => onChange('length_m', value)} />
      <NumberField label={t('field.width')} unit="m" value={config.width_m} min={1} onChange={value => onChange('width_m', value)} />
      <NumberField label={t('field.height')} unit="m" value={config.height_m} min={1} onChange={value => onChange('height_m', value)} />
      <NumberField label={t('field.wallHeight')} unit="m" value={config.H_pared_m} min={0} onChange={value => onChange('H_pared_m', value)} />
    </div>

    <SectionTitle title={t('section.trafficRoad')} />
    <div className="form-grid compact-grid">
      <NumberField label={t('field.lanes')} value={config.num_lanes} min={1} step={1} onChange={value => onChange('num_lanes', value)} />
      <NumberField label={t('field.laneWidth')} unit="m" value={config.lane_width_m} min={2.5} onChange={value => onChange('lane_width_m', value)} />
      <SelectField label={t('field.trafficDirection')} value={String(config.traffic_direction)} options={[["one_way", t('option.oneWay')], ["two_way", t('option.twoWay')]]} onChange={value => onChange('traffic_direction', value)} />
      <SelectField label={t('field.speed')} value={selectedSpeed} options={speedOptions.map(value => [String(value), `${value} km/h`])} onChange={value => onChange('speed_kmh', Number(value))} />
      <NumberField label={t('field.shoulderLeft')} unit="m" value={config.shoulder_left_m} min={0} onChange={value => onChange('shoulder_left_m', value)} />
      <NumberField label={t('field.shoulderRight')} unit="m" value={config.shoulder_right_m} min={0} onChange={value => onChange('shoulder_right_m', value)} />
      <NumberField label={t('field.sidewalkLeft')} unit="m" value={config.sidewalk_left_m} min={0} onChange={value => onChange('sidewalk_left_m', value)} />
      <NumberField label={t('field.sidewalkRight')} unit="m" value={config.sidewalk_right_m} min={0} onChange={value => onChange('sidewalk_right_m', value)} />
    </div>

    <div className="imd-card">
      <div className="imd-card-heading"><strong>{t('imd.title')}</strong><a href="https://mapadetrafico.transportes.gob.es/" target="_blank" rel="noopener noreferrer">{t('imd.dgt')}</a></div>
      <div className="form-grid compact-grid">
        <NumberField label={t('imd.aadt')} value={config.imd} min={0} max={200000} step={500} placeholder="15000" onChange={value => onChange('imd', value)} />
        <SelectField label={t('imd.kPeak')} value={kPeak.toFixed(2)} options={[["0.08", t('imd.kRural')], ["0.10", t('imd.kStandard')], ["0.11", t('imd.kMainRoad')], ["0.12", t('imd.kUrban')], ["0.14", t('imd.kCongested')]]} onChange={value => onChange('k_peak', Number(value))} />
      </div>
      <div className={`imd-calculation${imd > 0 ? ' active' : ''}`}>
        <span>{imd > 0 ? imd.toLocaleString('es-ES') : 'IMD'} × {kPeak.toFixed(2)}{isTwoWay ? '' : ' ÷ 2'} =</span>
        <strong>{imd > 0 ? designTrafficFromImd.toLocaleString('es-ES') : '—'} veh/h</strong>
        <small>({isTwoWay ? t('imd.twoWayTube') : t('imd.oneWayTube')})</small>
        <button type="button" className="imd-apply" onClick={() => onChange('traffic_veh_h', designTrafficFromImd)} disabled={imd <= 0}>{t('imd.apply')}</button>
      </div>
      <p className="imd-note">{t('imd.note')}</p>
    </div>

    <SectionTitle title={t('section.environment')} />
    <div className="form-grid compact-grid">
      <SelectField label={t('field.portalA')} value={String(config.portal_orientation)} options={orientations.map(value => [value, value])} onChange={value => onChange('portal_orientation', value)} />
      <label className="field"><span>{t('field.portalB')}</span><input value={`${portalB} · ${t('option.calculated')}`} readOnly /></label>
      <SelectField label={t('field.designSky')} value={String(config.sky_condition)} options={[["clear", t('option.clear')], ["intermediate", t('option.intermediate')], ["overcast", t('option.overcast')]]} onChange={value => onChange('sky_condition', value)} />
      <SelectField label={t('field.daylight')} value={String(config.daylight_penetration)} options={[["poor", t('option.poor')], ["good", t('option.good')]]} onChange={value => onChange('daylight_penetration', value)} />
      <SelectField label={t('field.roadSurface')} value={String(config.road_surface)} options={[["dark_asphalt", t('option.darkAsphalt')], ["medium_asphalt", t('option.mediumAsphalt')], ["light_asphalt", t('option.lightAsphalt')], ["concrete", t('option.concrete')], ["bright_concrete", t('option.brightConcrete')]]} onChange={value => onChange('road_surface', value)} />
      <NumberField label={t('field.wallReflectance')} unit="ρ" value={config.wall_reflectance} min={0.05} max={0.95} step={0.05} onChange={value => onChange('wall_reflectance', value)} />
    </div>

    <SectionTitle title={t('section.calculation')} />
    <div className="form-grid compact-grid">
      <SelectField label={t('field.l20Method')} value={String(config.l20_method)} options={[["model", t('option.model')], ["table", t('option.table')]]} onChange={value => onChange('l20_method', value)} />
      <NumberField label={t('field.gradient')} unit="%" value={config.gradient_pct} onChange={value => onChange('gradient_pct', value)} />
      <NumberField label={t('field.ambientTemp')} unit="°C" value={config.ta_design_c} onChange={value => onChange('ta_design_c', value)} />
      <NumberField label={t('field.designTraffic')} unit="veh/h" value={config.traffic_veh_h} min={0} onChange={value => onChange('traffic_veh_h', value)} />
      <NumberField label={t('field.reaction')} unit="s" value={config.t_reaction} min={0.5} onChange={value => onChange('t_reaction', value)} />
      <NumberField label={t('field.friction')} value={config.mu_friction} min={0} max={1} placeholder={t('option.autoPlaceholder')} onChange={value => onChange('mu_friction', value)} />
      <Toggle label={t('field.exitVisible')} checked={Boolean(config.exit_visible)} onChange={value => onChange('exit_visible', value)} />
      <Toggle label={t('field.roadLit')} checked={Boolean(config.illuminated_road)} onChange={value => onChange('illuminated_road', value)} />
    </div>
  </Panel>;
}

function LuminairePanel({ config, onChange, onConfigChange }: { config: TunnelConfig; onChange: (key: string, value: unknown) => void; onConfigChange: (key: string, value: unknown) => void }) {
  const { t } = useI18n();
  const lum = (config.lum_config && typeof config.lum_config === 'object') ? config.lum_config as TunnelConfig : {};
  const update = (key: string, value: unknown) => onChange(key, value);
  const updateConfig = (key: string, value: unknown) => onConfigChange(key, value);
  const rawMinCurrent = Number(lum.I_min_pct);
  const minCurrentPct = Number.isFinite(rawMinCurrent) ? (rawMinCurrent <= 1 ? rawMinCurrent * 100 : rawMinCurrent) : 30;
  const daylightEnabled = Boolean(lum.daylight_contribution_enabled || lum.exterior_layer_enabled);
  const physicalReoptimization = lum.auto_physical_reoptimization !== false;
  return <Panel title={t('panel.luminaireTitle')} intro={t('panel.luminaireIntro')}>
    <div className="luminaire-summary"><span className="luminaire-summary-icon">✦</span><div><strong>{t('luminaire.summaryTitle')}</strong><p>{t('luminaire.summaryHint')}</p></div></div>
    <SectionTitle title={t('section.luminaireGeometry')} />
    <div className="form-grid compact-grid luminaire-form-grid">
      <SelectField label={t('field.arrangement')} value={String(lum.arrangement || 'bilateral_sym')} options={[["central_single", t('option.centralSingle')], ["central_double", t('option.centralDouble')], ["central_offset", t('option.centralOffset')], ["lateral_left", t('option.lateralLeft')], ["lateral_right", t('option.lateralRight')], ["bilateral_sym", t('option.bilateral')], ["bilateral_stag", t('option.staggered')]]} onChange={value => update('arrangement', value)} />
      <NumberField label={t('field.mountingHeight')} unit="m" value={lum.mounting_height_m ?? 4.5} min={1.5} max={12} step={0.1} onChange={value => update('mounting_height_m', value)} />
      <NumberField label={t('field.minSpacing')} unit="m" value={lum.d_min ?? 2.5} min={0.3} max={10} step={0.5} onChange={value => update('d_min', value)} />
      <NumberField label={t('field.fixedSpacing')} unit="m" value={lum.d_fixed ?? ''} min={1} max={50} step={0.5} placeholder={t('option.autoPlaceholder')} onChange={value => update('d_fixed', value)} />
      <NumberField label={t('field.wallOffset')} unit="m" value={lum.wall_offset_m ?? 0.3} min={0} max={10} step={0.05} onChange={value => update('wall_offset_m', value)} />
      <NumberField label={t('field.axisOffset')} unit="m" value={lum.axis_offset_m ?? 0.3} min={0} max={10} step={0.05} onChange={value => update('axis_offset_m', value)} />
      <SelectField label={t('field.luminaireRoadSurface')} value={String(lum.road_surface || config.road_surface || 'medium_asphalt')} options={[["dark_asphalt", t('option.darkAsphalt')], ["medium_asphalt", t('option.mediumAsphalt')], ["light_asphalt", t('option.lightAsphalt')], ["concrete", t('option.concrete')], ["bright_concrete", t('option.brightConcrete')]]} onChange={value => update('road_surface', value)} />
    </div>
    <p className="luminaire-section-note">{t('luminaire.geometryHint')}</p>

    <SectionTitle title={t('section.luminaireOptimization')} />
    <div className="form-grid compact-grid luminaire-form-grid">
      <SelectField label={t('field.optimizationGoal')} value={String(lum.optimization_goal || 'min_luminaires')} options={[["min_luminaires", t('option.minLuminaires')], ["min_power", t('option.minPower')]]} onChange={value => update('optimization_goal', value)} />
      <NumberField label={t('field.transitionSpacing')} unit="m" value={lum.transition_spacing_step_m ?? 2} min={0.5} max={10} step={0.5} onChange={value => update('transition_spacing_step_m', value)} />
      {String(lum.optimization_goal || 'min_luminaires') === 'min_power' && <>
        <NumberField label={t('field.maxLuminaireIncrease')} unit="%" value={lum.max_luminaire_increase_pct ?? 15} min={0} max={500} step={1} onChange={value => update('max_luminaire_increase_pct', value)} />
        <NumberField label={t('field.maxBaseReduction')} unit="%" value={lum.max_base_spacing_reduction_pct ?? 20} min={0} max={95} step={1} onChange={value => update('max_base_spacing_reduction_pct', value)} />
      </>}
    </div>
    <div className="luminaire-toggle-stack">
      <Toggle label={t('field.autoPhysicalReoptimization')} checked={physicalReoptimization} onChange={value => update('auto_physical_reoptimization', value)} />
    </div>
    {physicalReoptimization && <div className="form-grid compact-grid luminaire-form-grid nested-luminaire-grid">
      <NumberField label={t('field.sceneSpacingReduction')} unit="%" value={lum.scene_reoptimization_max_spacing_reduction_pct ?? 35} min={0} max={80} step={1} onChange={value => update('scene_reoptimization_max_spacing_reduction_pct', value)} />
      <NumberField label={t('field.physicalAlternatives')} value={lum.scene_reoptimization_max_attempts ?? 3} min={1} max={4} step={1} onChange={value => update('scene_reoptimization_max_attempts', value)} />
    </div>}
    <div className="form-grid compact-grid luminaire-form-grid">
      <NumberField label={t('field.constructiveSeparation')} unit="m" value={lum.constructive_min_separation_m ?? 0.5} min={0.05} max={5} step={0.05} onChange={value => update('constructive_min_separation_m', value)} />
      <NumberField label={t('field.spacingQuantum')} unit="m" value={lum.spacing_quantum_m ?? 0.5} min={0.5} max={5} step={0.5} onChange={value => update('spacing_quantum_m', value)} />
    </div>
    <p className="luminaire-section-note">{t('luminaire.optimizationHint')}</p>

    <SectionTitle title={t('section.luminaireDaylight')} />
    <div className="luminaire-toggle-stack">
      <Toggle label={t('field.daylightContribution')} checked={daylightEnabled} onChange={value => update('daylight_contribution_enabled', value)} />
    </div>
    {daylightEnabled && <div className="form-grid compact-grid luminaire-form-grid nested-luminaire-grid">
      <NumberField label={t('field.daylightLength')} unit="m" value={lum.daylight_penetration_length_m ?? 60} min={5} max={250} step={1} onChange={value => update('daylight_penetration_length_m', value)} />
      <NumberField label={t('field.daylightMouth')} unit="% Lth" value={lum.daylight_mouth_contribution_pct ?? 10} min={1} max={50} step={1} onChange={value => update('daylight_mouth_contribution_pct', value)} />
      <div className="field daylight-portals"><span>{t('field.daylightPortals')}</span><div className="daylight-portal-options"><label><input type="checkbox" checked={lum.daylight_portal_a !== false} onChange={event => update('daylight_portal_a', event.target.checked)} /> A</label><label><input type="checkbox" checked={lum.daylight_portal_b !== false} onChange={event => update('daylight_portal_b', event.target.checked)} /> B</label></div></div>
      <div className="field-display"><span>{t('field.daylightProfile')}</span><strong>{t('luminaire.daylightProfileValue')}</strong></div>
    </div>}
    <p className="luminaire-section-note">{t('luminaire.daylightHint')}</p>

    <SectionTitle title={t('section.luminaireSource')} />
    <div className="form-grid compact-grid luminaire-form-grid">
      <SelectField label={t('field.optic')} value={String(lum.optic || 'F151')} options={[["auto", t('option.autoOptic')], ["F151", "F151"], ["F2MD", "F2MD"], ["F2M2", "F2M2"]]} onChange={value => update('optic', value)} />
      <SelectField label={t('field.cct')} value={String(lum.cct || '4000K')} options={[["4000K", "4000 K"], ["3000K", "3000 K"]]} onChange={value => update('cct', value)} />
      <NumberField label={t('field.minCurrent')} unit="%" value={minCurrentPct} min={20} max={50} step={5} onChange={value => update('I_min_pct', value)} />
      <NumberField label={t('field.maxCurrent')} unit="mA" value={lum.I_max_mA ?? 750} min={105} max={1050} step={5} onChange={value => update('I_max_mA', value)} />
      <NumberField label={t('field.tiltMax')} unit="°" value={lum.tilt_max ?? 20} min={0} max={45} step={1} onChange={value => update('tilt_max', value)} />
      <NumberField label={t('field.maintenance')} value={lum.maintenance_factor ?? 0.8} min={0.1} max={1} step={0.05} onChange={value => update('maintenance_factor', value)} />
    </div>

    <SectionTitle title={t('section.luminaireQuality')} />
    <div className="form-grid compact-grid luminaire-form-grid">
      <NumberField label={t('field.u0')} value={lum.U0_obj ?? 0.4} min={0.1} max={1} step={0.01} onChange={value => update('U0_obj', value)} />
      <NumberField label={t('field.ul')} value={lum.Ul_obj ?? 0.6} min={0.1} max={1} step={0.01} onChange={value => update('Ul_obj', value)} />
      <NumberField label={t('field.sceneExcess')} unit="%" value={lum.scene_excess_ratio_pct ?? 4} min={1} max={20} step={1} onChange={value => update('scene_excess_ratio_pct', value)} />
      <NumberField label={t('field.luminanceMargin')} unit="%" value={lum.luminance_margin_pct ?? 4} min={0} max={15} step={1} onChange={value => update('luminance_margin_pct', value)} />
    </div>
    <p className="luminaire-section-note">{t('luminaire.qualityHint')}</p>

    <SectionTitle title={t('section.luminaireCie')} />
    <div className="form-grid compact-grid luminaire-form-grid">
      <NumberField label={t('field.rhoWall')} value={config.rho_wall ?? 0.4} min={0.05} max={0.95} step={0.05} onChange={value => updateConfig('rho_wall', value)} />
      <NumberField label={t('field.rhoCeiling')} value={config.rho_ceiling ?? 0.25} min={0.05} max={0.95} step={0.05} onChange={value => updateConfig('rho_ceiling', value)} />
      <NumberField label={t('workspace.wallHeightEval')} unit="m" value={config.wall_luminance_height_m ?? 2} min={0.5} max={5.5} step={0.1} onChange={value => updateConfig('wall_luminance_height_m', value)} />
      <NumberField label={t('workspace.wallRatio')} value={config.wall_ratio_override ?? ''} min={0.05} max={2} step={0.01} placeholder={t('option.autoPlaceholder')} onChange={value => updateConfig('wall_ratio_override', value)} />
      <SelectField label={t('workspace.calcMode')} value={String(config.calc_mode || 'direct')} options={[["direct", t('workspace.direct')], ["radiosity", t('workspace.radiosity')]]} onChange={value => updateConfig('calc_mode', value)} />
    </div>
    <p className="luminaire-section-note">{t('luminaire.cieHint')}</p>
    <div className="luminaire-note">{t('luminaire.engineNote')}</div>
  </Panel>;
}

function TunnelSectionPreview({ config }: { config: TunnelConfig }) {
  const { t } = useI18n();
  const width = Math.max(1, Number(config.width_m) || 10.5); const height = Math.max(1, Number(config.height_m) || 5.5); const lanes = Math.max(1, Math.round(Number(config.num_lanes) || 2)); const laneWidth = Math.max(1, Number(config.lane_width_m) || width / lanes); const left = Math.max(0, Number(config.sidewalk_left_m) || 0) + Math.max(0, Number(config.shoulder_left_m) || 0); const right = Math.max(0, Number(config.sidewalk_right_m) || 0) + Math.max(0, Number(config.shoulder_right_m) || 0); const road = Math.max(1, width - left - right); const scale = Math.min(58, 740 / width, 300 / height); const roadWidth = road * scale; const roadX = 440 - roadWidth / 2; const baseY = 335; const wallHeight = Math.min(250, height * scale); const roof = String(config.tunnel_shape) === 'rectangular' ? `M${roadX},${baseY - wallHeight} H${roadX + roadWidth} V${baseY} H${roadX} Z` : `M${roadX},${baseY} V${baseY - wallHeight * .55} Q440,${baseY - wallHeight * 1.15} ${roadX + roadWidth},${baseY - wallHeight * .55} V${baseY} Z`;
  const shape = String(config.tunnel_shape) === 'rectangular' ? t('preview.rectangular') : String(config.tunnel_shape) === 'circular' ? t('preview.circular') : t('preview.horseshoe');
  return <section className="section-preview technical-view-card"><div className="preview-heading"><div><span className="eyebrow">VISTA TRANSVERSAL</span><h2>{t('preview.section', { tube: String(config.tube_id || 'T1') })}</h2></div><span className="preview-badge">{shape}</span></div><svg className="tunnel-svg" viewBox="0 0 880 430" role="img" aria-label={t('preview.aria')}><rect x="35" y="345" width="810" height="52" rx="7" fill="#e8e2d8" /><path d={roof} fill="#252525" stroke="#3d3d3d" strokeWidth="5" /><line x1={roadX} y1={baseY} x2={roadX + roadWidth} y2={baseY} stroke="#c9a227" strokeWidth="4" /><line x1={roadX + roadWidth / 2} y1={baseY} x2={roadX + roadWidth / 2} y2={baseY - 6} stroke="#c9a227" strokeWidth="3" />{Array.from({ length: lanes - 1 }).map((_, i) => <line key={i} x1={roadX + (roadWidth / lanes) * (i + 1)} y1={baseY - 2} x2={roadX + (roadWidth / lanes) * (i + 1)} y2={baseY - 13} stroke="#c9a227" strokeWidth="2" />)}<line x1={roadX - 23} y1={baseY} x2={roadX - 23} y2={baseY - wallHeight} stroke="#a09a91" /><line x1={roadX + roadWidth + 23} y1={baseY} x2={roadX + roadWidth + 23} y2={baseY - wallHeight} stroke="#a09a91" /><text x={440} y={390} textAnchor="middle" className="dimension">{t('preview.totalWidth', { value: width.toFixed(2) })}</text><text x={roadX - 28} y={baseY - wallHeight / 2} textAnchor="end" className="dimension">{height.toFixed(2)} m</text><text x={440} y={baseY - wallHeight - 18} textAnchor="middle" className="preview-label">{t('preview.lanes', { count: lanes, value: laneWidth.toFixed(2) })}</text><text x={roadX - 10} y={baseY + 23} textAnchor="end" className="dimension">{left.toFixed(2)} m</text><text x={roadX + roadWidth + 10} y={baseY + 23} className="dimension">{right.toFixed(2)} m</text></svg></section>;
}

function TunnelAxonometricPreview({ config }: { config: TunnelConfig }) {
  const width = Math.max(1, numberValue(config.width_m, 10.5));
  const height = Math.max(1, numberValue(config.height_m, 5.5));
  const length = Math.max(10, numberValue(config.length_m, 300));
  const lanes = Math.max(1, Math.round(numberValue(config.num_lanes, 2)));
  const shape = String(config.tunnel_shape || 'horseshoe');
  const roadWidth = Math.min(260, 158 + width * 9);
  const nearLeft = 152;
  const nearRight = nearLeft + roadWidth;
  const farLeft = 510;
  const farRight = 510 + roadWidth * .54;
  const nearCrown = Math.max(112, 270 - height * 12);
  const farCrown = 100;
  const laneOffsets = Array.from({ length: lanes - 1 }, (_, index) => 1 + index);
  const nearWallTop = shape === 'rectangular' ? nearCrown : 258;
  const farWallTop = shape === 'rectangular' ? farCrown : 153;
  const shell = shape === 'rectangular'
    ? `M${nearLeft} 326 V${nearCrown} H${nearRight} V326 L${farRight} 190 V${farCrown} H${farLeft} V190 Z`
    : shape === 'circular'
      ? `M${nearLeft} 326 V258 A${roadWidth / 2} ${Math.max(70, height * 10)} 0 0 1 ${nearRight} 258 V326 L${farRight} 190 V153 A${(farRight - farLeft) / 2} 64 0 0 1 ${farLeft} 153 V190 Z`
      : `M${nearLeft} 326 V258 Q${nearLeft + roadWidth / 2} ${nearCrown} ${nearRight} 258 V326 L${farRight} 190 V153 Q${(farLeft + farRight) / 2} ${farCrown} ${farLeft} 153 V190 Z`;
  const roof = shape === 'rectangular'
    ? `M${nearLeft} ${nearCrown} H${nearRight} L${farRight} ${farCrown} H${farLeft} Z`
    : shape === 'circular'
      ? `M${nearLeft} 258 A${roadWidth / 2} ${Math.max(70, height * 10)} 0 0 1 ${nearRight} 258 L${farRight} 153 A${(farRight - farLeft) / 2} 64 0 0 1 ${farLeft} 153 Z`
      : `M${nearLeft} 258 Q${nearLeft + roadWidth / 2} ${nearCrown} ${nearRight} 258 L${farRight} 153 Q${(farLeft + farRight) / 2} ${farCrown} ${farLeft} 153 Z`;
  return <section className="axonometric-preview technical-view-card">
    <div className="technical-view-heading"><div><span className="eyebrow">VISTA ISOMÉTRICA</span><h3>Volumen del túnel</h3></div><span>{length.toFixed(0)} m</span></div>
    <svg viewBox="0 0 820 440" role="img" aria-label="Vista isométrica longitudinal del túnel">
      <defs><linearGradient id="iso-road-gradient" x1="0" x2="1"><stop stopColor="#34434b"/><stop offset="1" stopColor="#17232b"/></linearGradient><linearGradient id="iso-shell-gradient" x1="0" x2="0" y2="1"><stop stopColor="#697983"/><stop offset="1" stopColor="#36444d"/></linearGradient><pattern id="iso-grid" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M28 0H0V28" fill="none" stroke="#d9e2df" strokeWidth="1"/></pattern></defs>
      <rect width="820" height="440" rx="14" fill="#edf2f0"/><path d="M48 366 H770 V416 H48 Z" fill="url(#iso-grid)" opacity=".72"/>
      <path d={shell} fill="url(#iso-shell-gradient)" stroke="#26343d" strokeWidth="3"/>
      <path d={roof} fill="#596b75" opacity=".8"/>
      <path d={`M${nearLeft} ${nearWallTop} V326 L${farLeft} 190 V${farWallTop} Z`} fill="#485963" stroke="#26343d" strokeWidth="2"/><path d={`M${nearRight} ${nearWallTop} V326 L${farRight} 190 V${farWallTop} Z`} fill="#33434d" stroke="#26343d" strokeWidth="2"/>
      <path d={`M${nearLeft} 326 H${nearRight} L${farRight} 190 H${farLeft} Z`} fill="url(#iso-road-gradient)" stroke="#d1a92b" strokeWidth="2.5"/>
      <path d={`M${nearLeft + roadWidth / 2} 326 L${(farLeft + farRight) / 2} 190`} stroke="#e7d36c" strokeWidth="2" strokeDasharray="13 10"/>
      {laneOffsets.map(offset => { const ratio = offset / lanes; const xNear = nearLeft + roadWidth * ratio; const xFar = farLeft + (farRight - farLeft) * ratio; return <path key={offset} d={`M${xNear} 326 L${xFar} 190`} stroke="#e7d36c" strokeWidth="1.7" strokeDasharray="10 9" opacity=".9"/>; })}
      {[.16, .36, .56, .76, .92].map(ratio => { const x = nearLeft + (farLeft - nearLeft) * ratio; const y = nearWallTop + (farWallTop - nearWallTop) * ratio; const lampX = x + roadWidth * .5; const lampY = y - (nearCrown - 40) * (1 - ratio); return <g key={ratio}><line x1={lampX} x2={lampX} y1={lampY + 4} y2={y + 8} stroke="#d6e0dc" strokeWidth="1.5" opacity=".8"/><circle cx={lampX} cy={lampY} r="6" fill="#ffdc5c" stroke="#8f7417" strokeWidth="1.5"/><circle cx={lampX} cy={lampY} r="2" fill="#fff"/></g>; })}
      <path d="M92 382 H564" stroke="#8997a1" strokeWidth="1.5"/><path d="M92 376 V388 M564 376 V388" stroke="#8997a1" strokeWidth="1.5"/><text x="328" y="407" textAnchor="middle" fill="#53616c" fontSize="13" fontWeight="700">Longitud de referencia · {length.toFixed(0)} m</text>
      <text x="126" y="225" fill="#53616c" fontSize="12" fontWeight="800" letterSpacing="1.3">BOCA A</text><text x="650" y="142" fill="#53616c" fontSize="12" fontWeight="800" letterSpacing="1.3">BOCA B</text><text x="311" y="304" fill="#dbe6e4" fontSize="13" fontWeight="700">{lanes} carriles · {width.toFixed(1)} m · h {height.toFixed(1)} m · {shape === 'rectangular' ? 'Rectangular' : shape === 'circular' ? 'Circular' : 'Herradura'}</text>
    </svg>
  </section>;
}

function TunnelLongitudinalPreview({ config, result }: { config: TunnelConfig; result: Record<string, unknown> | null }) {
  const length = Math.max(10, numberValue(config.length_m, 300));
  const slope = numberValue(config.gradient_pct, 0);
  const laneCount = Math.max(1, Math.round(numberValue(config.num_lanes, 2)));
  const rawZones = Object.entries(record(result?.zones)).map(([key, value]) => {
    const zone = record(value);
    return { key, name: String(zone.zone_name || key), start: Math.max(0, numberValue(zone.s_start)), end: Math.min(length, numberValue(zone.s_end, length)) };
  }).filter(zone => zone.end > zone.start).sort((a, b) => a.start - b.start);
  const zones = rawZones.length ? rawZones : [{ key: 'interior', name: 'Interior zone', start: 0, end: length }];
  const zoneColors: Record<string, string> = { access: '#8f8a81', threshold: '#c58c2d', transition: '#47828a', interior: '#4a9a72', exit: '#806487', post_exit: '#b4a99e' };
  const x = (value: number) => 84 + Math.max(0, Math.min(length, value)) / length * 992;
  const luminaireCount = Math.max(5, Math.min(14, Math.round(length / 28)));
  return <section className="longitudinal-preview technical-view-card">
    <div className="technical-view-heading"><div><span className="eyebrow">PLANTA / LONGITUDINAL</span><h3>Modelo técnico y zonas CIE 88</h3></div><span>{length.toFixed(0)} m</span></div>
    <svg viewBox="0 0 1160 330" role="img" aria-label="Planta y vista longitudinal técnica del túnel">
      <defs><pattern id="longitudinal-grid" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" stroke="#d8e1dd" strokeWidth="1"/></pattern><linearGradient id="longitudinal-road-gradient" x1="0" x2="1"><stop stopColor="#26343c"/><stop offset="1" stopColor="#111b22"/></linearGradient></defs>
      <rect width="1160" height="330" rx="10" fill="#f1f5f3"/><rect x="34" y="22" width="1092" height="274" rx="8" fill="url(#longitudinal-grid)"/>
      <text x="54" y="48" fill="#5c6b70" fontSize="11" fontWeight="800" letterSpacing="1.4">EJE DEL TÚNEL · VISTA EN PLANTA</text>
      {zones.map(zone => <g key={zone.key}><rect x={x(zone.start)} y="72" width={Math.max(3, x(zone.end) - x(zone.start))} height="22" fill={zoneColors[zone.key] || '#8f8a81'} opacity=".9"/><text x={(x(zone.start) + x(zone.end)) / 2} y="87" textAnchor="middle" fill="#fff" fontSize="10" fontWeight="800">{zone.name}</text></g>)}
      <path d="M84 133 H1080 V225 H84 Z" fill="url(#longitudinal-road-gradient)" stroke="#26343c" strokeWidth="3"/>
      {Array.from({ length: laneCount - 1 }).map((_, index) => <line key={index} x1="84" x2="1080" y1={133 + 92 * (index + 1) / laneCount} y2={133 + 92 * (index + 1) / laneCount} stroke="#f1d86f" strokeWidth="2" strokeDasharray="18 13" opacity=".9"/>)}
      <line x1="84" x2="1080" y1="179" y2="179" stroke="#d5e0dc" strokeWidth="1.5" strokeDasharray="5 7" opacity=".7"/>
      {Array.from({ length: luminaireCount }).map((_, index) => { const position = length * ((index + 1) / (luminaireCount + 1)); return <g key={position}><circle cx={x(position)} cy="121" r="6" fill="#f6cb4e" stroke="#8b711f" strokeWidth="1.5"/><circle cx={x(position)} cy="237" r="6" fill="#f6cb4e" stroke="#8b711f" strokeWidth="1.5"/></g>; })}
      <g><circle cx="84" cy="179" r="16" fill="#fff" stroke="#25343b" strokeWidth="2"/><text x="84" y="184" textAnchor="middle" fill="#25343b" fontSize="12" fontWeight="800">A</text><text x="84" y="112" textAnchor="middle" fill="#5c6b70" fontSize="11" fontWeight="800">BOCA A · {String(config.portal_orientation || 'S')}</text></g>
      <g><circle cx="1080" cy="179" r="16" fill="#fff" stroke="#25343b" strokeWidth="2"/><text x="1080" y="184" textAnchor="middle" fill="#25343b" fontSize="12" fontWeight="800">B</text><text x="1080" y="112" textAnchor="middle" fill="#5c6b70" fontSize="11" fontWeight="800">BOCA B</text></g>
      <path d={slope >= 0 ? "M500 268 H650 M650 268 l-12 -7 M650 268 l-12 7" : "M650 268 H500 M500 268 l12 -7 M500 268 l12 7"} fill="none" stroke="#47747a" strokeWidth="2.5"/><text x="575" y="286" textAnchor="middle" fill="#47747a" fontSize="11" fontWeight="800">Pendiente {slope >= 0 ? '+' : ''}{slope.toFixed(2)} %</text>
      <path d="M84 310 H1080" stroke="#93a39f" strokeWidth="1.5"/><path d="M84 304 V316 M1080 304 V316" stroke="#93a39f" strokeWidth="1.5"/><text x="582" y="326" textAnchor="middle" fill="#5c6b70" fontSize="12" fontWeight="700">Longitud total · {length.toFixed(0)} m · {laneCount} carriles</text>
    </svg>
  </section>;
}

type TechnicalView = 'plan' | 'section' | 'isometric';

const technicalViewLabels: Record<TechnicalView, string> = {
  plan: 'Planta / Longitudinal',
  section: 'Sección transversal',
  isometric: 'Vista isométrica',
};

function TunnelTechnicalViewport({ config, result, view, onViewChange }: { config: TunnelConfig; result: Record<string, unknown> | null; view: TechnicalView; onViewChange: (view: TechnicalView) => void }) {
  const tabs: { id: TechnicalView; label: string }[] = Object.entries(technicalViewLabels).map(([id, label]) => ({ id: id as TechnicalView, label }));
  return <section className="tunnel-technical-viewport"><div className="technical-viewport-heading"><div><span className="eyebrow">VISTA TÉCNICA PRINCIPAL</span><h2>Geometría y carretera · {String(config.tube_id || 'T1')}</h2><p>Selecciona una vista para inspeccionar el modelo compartido del tubo</p></div><span className="technical-live-dot">En vivo</span></div><div className="technical-view-tabs" role="tablist" aria-label="Vistas técnicas">{tabs.map(tab => <button key={tab.id} type="button" role="tab" aria-selected={view === tab.id} className={view === tab.id ? 'active' : ''} onClick={() => onViewChange(tab.id)}>{tab.label}</button>)}</div><div className="technical-view-stage">{view === 'plan' && <TunnelLongitudinalPreview config={config} result={result}/>} {view === 'section' && <TunnelSectionPreview config={config}/>} {view === 'isometric' && <TunnelAxonometricPreview config={config}/>}</div><div className="technical-view-footer"><span>Una fuente de parámetros · tubo {String(config.tube_id || 'T1')}</span><span>Parámetros actualizados en tiempo real</span></div></section>;
}

function TunnelDefinitionView({ view, config, onChange, onLumChange, onViewChange }: { view: TechnicalView; config: TunnelConfig; onChange: (key: string, value: unknown) => void; onLumChange: (key: string, value: unknown) => void; onViewChange: (view: TechnicalView) => void }) {
  const { t } = useI18n();
  return <div className="tunnel-definition-view" id="tunnel-geometry-definition">
    <PortalGeometryCard key={String(config.tube_id || 'T1')} config={config} onChange={onChange} onLumChange={onLumChange} />
    <div className="definition-view-selector" role="tablist" aria-label="Dependencias de la definición">
      {(Object.entries(technicalViewLabels) as [TechnicalView, string][]).map(([id, label]) => <button key={id} type="button" role="tab" aria-selected={view === id} className={view === id ? 'active' : ''} onClick={() => onViewChange(id)}>{label}</button>)}
    </div>
    {view === 'plan' && <section className="tunnel-definition-group" aria-label="Parámetros de planta y carretera"><div className="definition-group-heading"><span className="eyebrow">PLANTA / CARRETERA</span><strong>Geometría longitudinal</strong><small>Estos valores alimentan la planta y el perfil longitudinal.</small></div><div className="form-grid compact-grid">
      <TextField label={t('field.tubeId')} value={String(config.tube_id || '')} onChange={value => onChange('tube_id', value)} />
      <NumberField label={t('field.length')} unit="m" value={config.length_m} min={10} onChange={value => onChange('length_m', value)} />
      <NumberField label={t('field.speed')} unit="km/h" value={config.speed_kmh} min={20} max={130} step={5} onChange={value => onChange('speed_kmh', value)} />
      <NumberField label={t('field.gradient')} unit="%" value={config.gradient_pct} onChange={value => onChange('gradient_pct', value)} />
      <NumberField label={t('field.curvature')} unit="m" value={config.curvature_radius_m} onChange={value => onChange('curvature_radius_m', value)} placeholder={t('option.straightPlaceholder')} />
      <SelectField label={t('field.portalA')} value={String(config.portal_orientation)} options={orientations.map(orientation => [orientation, orientation])} onChange={value => onChange('portal_orientation', value)} />
      <label className="field"><span>{t('field.portalB')}</span><input value={`${oppositeOrientation[String(config.portal_orientation)] || 'N'} · ${t('option.calculated')}`} readOnly /></label>
    </div></section>}
    {view === 'section' && <section className="tunnel-definition-group" aria-label="Parámetros de sección transversal"><div className="definition-group-heading"><span className="eyebrow">SECCIÓN TRANSVERSAL</span><strong>Geometría de la sección y plataforma</strong><small>Estos valores alimentan la sección y el ancho útil de la carretera.</small></div><div className="form-grid compact-grid">
      <NumberField label={t('field.width')} unit="m" value={config.width_m} min={1} onChange={value => onChange('width_m', value)} />
      <NumberField label={t('field.height')} unit="m" value={config.height_m} min={1} onChange={value => onChange('height_m', value)} />
      <NumberField label={t('field.lanes')} value={config.num_lanes} min={1} step={1} onChange={value => onChange('num_lanes', value)} />
      <NumberField label={t('field.laneWidth')} unit="m" value={config.lane_width_m} min={2.5} onChange={value => onChange('lane_width_m', value)} />
      <SelectField label={t('field.trafficDirection')} value={String(config.traffic_direction)} options={[["one_way", t('option.oneWay')], ["two_way", t('option.twoWay')]]} onChange={value => onChange('traffic_direction', value)} />
      <SelectField label={t('field.tunnelShape')} value={String(config.tunnel_shape)} options={[["horseshoe", t('option.horseshoe')], ["rectangular", t('option.rectangular')], ["circular", t('option.circular')]]} onChange={value => onChange('tunnel_shape', value)} />
      <NumberField label={t('field.shoulderLeft')} unit="m" value={config.shoulder_left_m} min={0} onChange={value => onChange('shoulder_left_m', value)} />
      <NumberField label={t('field.shoulderRight')} unit="m" value={config.shoulder_right_m} min={0} onChange={value => onChange('shoulder_right_m', value)} />
      <NumberField label={t('field.sidewalkLeft')} unit="m" value={config.sidewalk_left_m} min={0} onChange={value => onChange('sidewalk_left_m', value)} />
      <NumberField label={t('field.sidewalkRight')} unit="m" value={config.sidewalk_right_m} min={0} onChange={value => onChange('sidewalk_right_m', value)} />
      <NumberField label={t('field.wallHeight')} unit="m" value={config.H_pared_m} min={0} onChange={value => onChange('H_pared_m', value)} />
      <SelectField label={t('field.roadSurface')} value={String(config.road_surface)} options={[["dark_asphalt", t('option.darkAsphalt')], ["medium_asphalt", t('option.mediumAsphalt')], ["light_asphalt", t('option.lightAsphalt')], ["concrete", t('option.concrete')], ["bright_concrete", t('option.brightConcrete')]]} onChange={value => onChange('road_surface', value)} />
    </div><div className="design-toggles single-toggle"><Toggle label={t('field.includeShoulders')} checked={Boolean(config.include_shoulders_in_luminance_grid)} onChange={value => onChange('include_shoulders_in_luminance_grid', value)} /></div></section>}
    {view === 'isometric' && <section className="tunnel-definition-group tunnel-isometric-dependencies" aria-label="Dependencias de la vista isométrica"><div className="definition-group-heading"><span className="eyebrow">VISTA ISOMÉTRICA</span><strong>Vista combinada del mismo túnel</strong><small>No tiene un tercer formulario: combina la geometría longitudinal y la sección transversal compartidas.</small></div><div className="shared-geometry-summary"><div><span>Planta / longitudinal</span><strong>{formatNumber(config.length_m, 0)} m · {formatNumber(config.gradient_pct, 2)} %</strong></div><div><span>Sección transversal</span><strong>{formatNumber(config.width_m, 1)} × {formatNumber(config.height_m, 1)} m · {formatNumber(config.num_lanes, 0)} carriles</strong></div></div><p className="shared-geometry-note">La isométrica se actualiza con esos mismos valores. Abre el bloque correspondiente para editarlos:</p><div className="shared-geometry-actions"><button type="button" className="secondary" onClick={() => onViewChange('plan')}>Editar Planta / Longitudinal</button><button type="button" className="secondary" onClick={() => onViewChange('section')}>Editar Sección transversal</button></div></section>}
  </div>;
}

function ActiveStepParameters({ active, config, result, luminaires, control, technicalView, onTechnicalViewChange, onChange, onLumChange, t }: { active: WorkspaceTab; config: TunnelConfig; result: Record<string, unknown> | null; luminaires: Record<string, unknown> | null; control: Record<string, unknown> | null; technicalView: TechnicalView; onTechnicalViewChange: (view: TechnicalView) => void; onChange: (key: string, value: unknown) => void; onLumChange: (key: string, value: unknown) => void; t: (key: string, params?: Record<string, string | number>) => string }) {
  const [openTunnelBlock, setOpenTunnelBlock] = useState<'definition' | 'calculation'>('definition');
  useEffect(() => { if (active === 'tunnel') setOpenTunnelBlock('definition'); }, [active, technicalView]);
  const summary = record(result?.summary);
  const totals = record(record(luminaires?.luminaires).totals);
  const stageCopy: Record<WorkspaceTab, [string, string]> = {
    tunnel: ['Definición', 'Parámetros base del tubo'],
    zones: ['Zonas', 'Secuencia calculada'],
    luminaire: ['Luminarias', 'Configuración fotométrica'],
    control: ['Control', 'Escenas y regulación'],
    report: ['Informe', 'Entregables del proyecto'],
  };
  return <section className="active-parameters" aria-label="Parámetros del paso activo">
    <div className="active-parameters-heading"><span className="eyebrow">PASO ACTIVO</span><strong>{stageCopy[active][0]}</strong><small>{stageCopy[active][1]}</small></div>
    {active === 'tunnel' && <div className={`active-tunnel-config has-open-${openTunnelBlock}`}>
      <div className="config-accordion-tabs">
        <div className={`config-accordion ${openTunnelBlock === 'definition' ? 'is-open' : ''}`}>
          <button type="button" className="config-accordion-toggle" aria-expanded={openTunnelBlock === 'definition'} aria-controls="tunnel-definition-accordion" onClick={() => setOpenTunnelBlock('definition')}>
            <span className="config-accordion-index" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><path d="M3.5 5.5 8.5 3.5l7 2.5 5-2v14.5l-5 2-7-2.5-5 2Z"/><path d="M8.5 3.5V18M15.5 6v14.5"/></svg></span><span className="config-accordion-copy"><strong>Definición compartida</strong><small>Planta, sección e isométrica</small></span><span className="config-accordion-icon" aria-hidden="true">{openTunnelBlock === 'definition' ? '−' : '+'}</span>
          </button>
          {openTunnelBlock === 'definition' && <div id="tunnel-definition-accordion" className="config-accordion-content"><TunnelDefinitionView view={technicalView} config={config} onChange={onChange} onLumChange={onLumChange} onViewChange={onTechnicalViewChange} /></div>}
        </div>
        <div className={`config-accordion ${openTunnelBlock === 'calculation' ? 'is-open' : ''}`}>
          <button type="button" className="config-accordion-toggle" aria-expanded={openTunnelBlock === 'calculation'} aria-controls="tunnel-calculation-accordion" onClick={() => setOpenTunnelBlock('calculation')}>
            <span className="config-accordion-index" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 7h8M8 11h2M12 11h2M16 11h0M8 15h2M12 15h2M16 15h0M8 18h8"/></svg></span><span className="config-accordion-copy"><strong>Parámetros de cálculo</strong><small>Entorno, CIE 88 y distancia de parada</small></span><span className="config-accordion-icon" aria-hidden="true">{openTunnelBlock === 'calculation' ? '−' : '+'}</span>
          </button>
          {openTunnelBlock === 'calculation' && <div id="tunnel-calculation-accordion" className="config-accordion-content"><Parameters config={config} result={result} onChange={onChange}/></div>}
        </div>
      </div>
    </div>}
    {active === 'zones' && <div className="active-parameter-metrics"><MetricTile label="Lth" value={result?.success ? formatNumber(summary.Lth, 1) : '—'} unit="cd/m²"/><MetricTile label="Lin" value={result?.success ? formatNumber(summary.Lin, 1) : '—'} unit="cd/m²"/><MetricTile label="Parada" value={result?.success ? formatNumber(summary.SD_m, 0) : '—'} unit="m"/><p>{result?.success ? 'Zonas listas para revisar.' : 'Calcula el túnel para generar zonas.'}</p></div>}
    {active === 'luminaire' && <div className="active-luminaire-config"><LuminairePanel config={config} onChange={onLumChange} onConfigChange={onChange}/><div className="active-parameter-status"><span>Estado</span><strong>{luminaires ? `${numberValue(totals.n_luminaires, 0)} luminarias` : 'Pendiente de cálculo'}</strong></div></div>}
    {active === 'control' && <div className="active-control-settings"><h3>Parámetros de control</h3><p>Configura protocolo, sensores, escenas y regulación sin abandonar la vista técnica.</p><ControlSettings config={config} onChange={onChange} t={t}/><div className="active-parameter-status"><span>Estado</span><strong>{control ? 'Escenas calculadas' : 'Pendiente de cálculo'}</strong></div></div>}
    {active === 'report' && <div className="active-report-settings"><ReportOptionsPanel config={config} onChange={onChange} t={t}/><div className="active-parameter-status"><span>Preparación</span><strong>{control ? 'Informe listo' : 'Completa las fases previas'}</strong></div><p>DOCX y XLSX con trazabilidad de parámetros, normativa y resultados.</p></div>}
  </section>;
}

function ReportOptionsPanel({ config, onChange, t }: { config: TunnelConfig; onChange: (key: string, value: unknown) => void; t: (key: string, params?: Record<string, string | number>) => string }) {
  return <div className="report-options-inline"><SectionTitle title={t('section.reportOptions')} /><div className="form-grid compact-grid"><SelectField label={t('field.reportVersion')} value={String(config.report_version || 'v2')} options={[["v2", t('option.reportV2')], ["v1", t('option.reportV1')]]} onChange={value => onChange('report_version', value)} /><label className="field"><span>{t('field.reportVideoTitle')}</span><input value={String(config.report_video_title || '')} onChange={event => onChange('report_video_title', event.target.value)} /></label><label className="field"><span>{t('field.reportVideoUrl')}</span><input type="url" value={String(config.report_video_url || '')} onChange={event => onChange('report_video_url', event.target.value)} placeholder="https://…" /></label></div></div>;
}

function LiveEngineeringSummary({ config, result, luminaires, control, active, stageStale }: { config: TunnelConfig; result: Record<string, unknown> | null; luminaires: Record<string, unknown> | null; control: Record<string, unknown> | null; active: WorkspaceTab; stageStale: StageStale }) {
  const summary = record(result?.summary);
  const photometric = record(luminaires?.photometric);
  const warnings = Array.isArray(result?.warnings) ? result.warnings.map(String).slice(0, 3) : [];
  const status = stageStale.tunnel ? { label: 'Cambios pendientes de calcular', tone: 'warning' } : result?.success ? { label: 'CIE 88 calculado', tone: 'ready' } : { label: 'Pendiente de calcular', tone: 'pending' };
  const compliance = photometric.overall_compliant === true ? 'Cumple CIE 140' : photometric.overall_compliant === false ? 'Revisar cumplimiento' : 'CIE 140 pendiente';
  const activePhase: Record<WorkspaceTab, string> = { tunnel: 'Túnel', zones: 'Zonas', luminaire: 'Luminarias', control: 'Control', report: 'Informe' };
  return <aside className="studio-insights engineering-summary"><div className="insight-heading"><span>ESTADO DEL PROYECTO</span><span className={`insight-dot ${status.tone === 'ready' ? 'ready' : ''}`}/></div><section className={`summary-status-card ${status.tone}`}><span className="summary-status-label">Estado del cálculo</span><strong>{status.label}</strong><small>Fase activa · {activePhase[active]}</small></section><section className="summary-spec-card"><div><span>Normativa</span><strong>CIE 88 · CIE 140</strong></div><div><span>Tubo activo</span><strong>{String(config.tube_id || 'T1')}</strong></div><div><span>Sección</span><strong>{numberValue(config.width_m, 0).toFixed(1)} × {numberValue(config.height_m, 0).toFixed(1)} m</strong></div><div><span>Longitud</span><strong>{numberValue(config.length_m, 0).toFixed(0)} m</strong></div></section><section className="summary-result-card"><div><span>Resultado clave</span><strong>{result?.success ? `${numberValue(summary.Lth, 0).toFixed(1)} cd/m²` : '—'}</strong><small>{result?.success ? `Lth · Lin ${numberValue(summary.Lin, 0).toFixed(1)} cd/m²` : 'Calcula CIE 88 para generar las zonas'}</small></div><div className={photometric.overall_compliant === true ? 'summary-compliance ready' : photometric.overall_compliant === false ? 'summary-compliance warning' : 'summary-compliance pending'}>{compliance}</div></section>{control && <div className="summary-control-ready">✓ Control y escenas calculados</div>}{warnings.length > 0 && <section className="summary-warnings"><strong>Advertencias</strong>{warnings.map(warning => <p key={warning}>⚠ {warning}</p>)}</section>}</aside>;
}

function PortalGeometryCard({ config, onChange, onLumChange }: { config: TunnelConfig; onChange: (key: string, value: unknown) => void; onLumChange: (key: string, value: unknown) => void }) {
  const { t } = useI18n();
  const [mode, setMode] = useState(String(config.portal_mode || 'manual'));
  const [images, setImages] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [laneRef, setLaneRef] = useState(Number(config.portal_lane_ref_m) || 3.5);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState('');
  const [warnings, setWarnings] = useState<string[]>([]);

  const portalGeometry = (config.portal_geometry && typeof config.portal_geometry === 'object')
    ? config.portal_geometry as Record<string, Record<string, unknown>> : {};
  const hasProposal = Object.keys(portalGeometry).length > 0;

  const chooseMode = (next: string) => { setMode(next); onChange('portal_mode', next); setError(''); };
  const onFilesChosen = (event: ChangeEvent<HTMLInputElement>) => {
    const nextFiles = Array.from(event.target.files || []).slice(0, 2);
    setImages(nextFiles);
    setPreviews(nextFiles.map(file => URL.createObjectURL(file)));
  };
  const analyze = async () => {
    if (!images.length) return;
    setAnalyzing(true); setError(''); setWarnings([]); onChange('portal_lane_ref_m', laneRef);
    try {
      const body = new FormData();
      images.forEach(file => body.append('images', file));
      body.append('lane_width_ref_m', String(laneRef));
      const response = await fetch('/api/tunnel/portal-analyze', { method: 'POST', body });
      const data = await response.json();
      if (!data.success) { setError(data.error || t('geometry.analysisError')); return; }
      const proposed: Record<string, Record<string, unknown>> = {};
      Object.entries(data.fields || {}).forEach(([key, field]) => {
        proposed[key] = { ...(field as Record<string, unknown>), status: 'proposed', originalValue: (field as Record<string, unknown>).value };
      });
      onChange('portal_geometry', proposed);
      setWarnings(Array.isArray(data.warnings) ? data.warnings : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('geometry.connectionError'));
    } finally { setAnalyzing(false); }
  };
  const applyProposal = () => {
    const value = (key: string) => portalGeometry[key]?.value;
    ['num_lanes', 'lane_width_m', 'shoulder_left_m', 'shoulder_right_m', 'sidewalk_left_m', 'sidewalk_right_m', 'width_m', 'height_m', 'H_pared_m', 'tunnel_shape']
      .forEach(key => { if (value(key) !== undefined && value(key) !== null) onChange(key, value(key)); });
    const lumPatch: Record<string, unknown> = {};
    if (value('mounting_height_m') !== undefined) lumPatch.mounting_height_m = value('mounting_height_m');
    if (value('wall_offset_m') !== undefined) lumPatch.wall_offset_m = value('wall_offset_m');
    if (Object.keys(lumPatch).length) Object.entries(lumPatch).forEach(([key, next]) => onLumChange(key, next));
  };

  return <section className="portal-source-card">
    <div className="portal-source-heading"><div><span className="portal-source-icon" aria-hidden="true">▧</span><strong>{t('geometry.sourceTitle')}</strong></div><span className="portal-source-state">{mode === 'image' ? t('geometry.imageMode') : t('geometry.manualMode')}</span></div>
    <div className="portal-source-actions">
      <button type="button" className={mode === 'manual' ? 'portal-mode active' : 'portal-mode'} onClick={() => chooseMode('manual')}>{t('geometry.manual')}</button>
      <button type="button" className={mode === 'image' ? 'portal-mode active' : 'portal-mode'} onClick={() => chooseMode('image')}>{t('geometry.fromImage')}</button>
    </div>
    {mode === 'image' && <div className="portal-image-tools">
      <p>{t('geometry.imageHint')}</p>
      <div className="portal-image-fields"><label className="field"><span>{t('geometry.images')}</span><input type="file" accept="image/*" multiple onChange={onFilesChosen} /></label><NumberField label={t('geometry.referenceLane')} unit="m" value={laneRef} min={2.5} max={4.5} step={0.05} onChange={value => setLaneRef(Number(value) || 3.5)} /></div>
      {previews.length > 0 && <div className="portal-previews">{previews.map((preview, index) => <img key={preview} src={preview} alt={t('geometry.previewAlt', { index: index + 1 })} />)}</div>}
      <button type="button" className="secondary portal-analyze" onClick={() => void analyze()} disabled={!images.length || analyzing}>{analyzing ? t('geometry.analyzing') : t('geometry.analyze')}</button>
      {error && <div className="portal-message error">{error}</div>}
      {warnings.map(warning => <div className="portal-message warning" key={warning}>{warning}</div>)}
      {hasProposal && <button type="button" className="primary portal-apply" onClick={applyProposal}>{t('geometry.apply')}</button>}
    </div>}
  </section>;
}

function GeometryDecision({ config }: { config: TunnelConfig }) {
  const { t } = useI18n();
  const portalB = oppositeOrientation[String(config.portal_orientation)] || 'N';
  const traffic = String(config.traffic_direction) === 'two_way' ? t('option.twoWay') : t('option.oneWay');
  const rows: [string, string][] = [
    [t('decision.length'), `${formatNumber(config.length_m, 0)} m`],
    [t('decision.width'), `${formatNumber(config.width_m, 1)} m`],
    [t('decision.height'), `${formatNumber(config.height_m, 1)} m`],
    [t('decision.lanes'), formatNumber(config.num_lanes, 0)],
    [t('decision.laneWidth'), `${formatNumber(config.lane_width_m, 1)} m`],
    [t('decision.shoulders'), `${formatNumber(config.shoulder_left_m, 1)} / ${formatNumber(config.shoulder_right_m, 1)} m`],
    [t('decision.sidewalks'), `${formatNumber(config.sidewalk_left_m, 1)} / ${formatNumber(config.sidewalk_right_m, 1)} m`],
    [t('decision.traffic'), traffic],
    [t('decision.gradient'), `${formatNumber(config.gradient_pct, 0)} %`],
    [t('decision.portal'), String(config.portal_orientation || 'S')],
  ];
  return <section className="decision-panel"><div className="decision-kicker">{t('decision.title')}</div><h2>{t('decision.geometry')}</h2><div className="decision-list">{rows.map(([label, value]) => <div className="decision-row" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div><div className="decision-note">{t('decision.opposite', { portal: portalB })}</div></section>;
}

type ValidationState = { valid: boolean; errors: string[]; warnings: string[] };
type WorkspaceTab = 'tunnel' | 'zones' | 'luminaire' | 'control' | 'report';
type StageStale = { tunnel: boolean; luminaire: boolean; control: boolean };

const cieInputKeys = new Set(['project_name', 'tube_id', 'length_m', 'speed_kmh', 'gradient_pct', 'curvature_radius_m', 'traffic_direction', 'mu_friction', 't_reaction', 'width_m', 'height_m', 'num_lanes', 'lane_width_m', 'shoulder_left_m', 'shoulder_right_m', 'sidewalk_left_m', 'sidewalk_right_m', 'include_shoulders_in_luminance_grid', 'portal_orientation', 'portal_geometry', 'portal_mode', 'portal_lane_ref_m', 'tunnel_shape', 'H_pared_m', 'road_surface', 'environment_type', 'sky_condition', 'daylight_penetration', 'wall_reflectance', 'rho_wall', 'rho_ceiling', 'wall_luminance_height_m', 'wall_ratio_override', 'exit_visible', 'illuminated_road', 'traffic_veh_h', 'imd', 'k_peak', 'has_pedestrians', 'interior_luminance_override', 'l20_method', 'lth_method', 'lth_standard', 'tunnel_class', 'l20_override', 'l20_b_override', 'lth_override', 'lth_b_override', 'lseq_override', 'lseq_b_override', 'qc_override', 'contrast_observation', 'profile_stepped', 'n_steps', 'threshold_length_override_m', 'threshold_length_b_override_m', 'transition_end_override_m', 'transition_end_b_override_m', 'exit_length_override_m', 'exit_luminance_ratio_override', 'k_lth_override', 'k_lth_b_override', 'dp_override', 'dp_b_override', 'stopping_distance_override_m', 'stopping_distance_b_override_m', 'ta_design_c']);
const luminaireInputKeys = new Set(['calc_mode', 'rho_wall', 'rho_ceiling', 'wall_luminance_height_m', 'wall_ratio_override', 'tilt_overrides', 'tandem_overrides', 'manual_luminaire_overrides', 'scene_current_overrides', 'control_architecture']);
const controlInputKeys = new Set(['n_transition_groups', 'annual_operation_hours', 'night_operation_hours', 'night_reduced_share_pct', 'energy_tariff_eur_kwh', 'night_normal_luminance_cd_m2', 'night_reduced_luminance_cd_m2', 'control_protocol', 'control_topology', 'sensor_type', 'sample_interval_min', 'ramp_time_s', 'dim_min_pct', 'dim_max_pct', 'driver_min_dim_pct', 'wirepas_nodes_per_gateway', 'dali_max_addresses_per_line', 'dali_group_span_m', 'dali_cabinet_position_m', 'control_architecture']);

function record(value: unknown): Record<string, unknown> { return value && typeof value === 'object' ? value as Record<string, unknown> : {}; }
function numberValue(value: unknown, fallback = 0): number { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : fallback; }
function MetricTile({ label, value, unit }: { label: string; value: unknown; unit?: string }) { return <div className="metric-tile"><small>{label}</small><strong>{value === undefined || value === null || value === '' ? '—' : String(value)}</strong>{unit && <em>{unit}</em>}</div>; }

function WorkspaceOverview({ project, config, result, onNavigate, t }: { project: ProjectRecord; config: TunnelConfig; result: Record<string, unknown> | null; onNavigate: (tab: WorkspaceTab) => void; t: (key: string, params?: Record<string, string | number>) => string }) {
  const summary = record(result?.summary);
  const hasResult = result?.success === true;
  return <div className="workspace-board overview-board">
    <div className="board-heading"><div><span className="eyebrow">SALVI TUNNEL ENGINE</span><h2>{t('workspace.overview')}</h2><p>{t('workspace.overviewHint')}</p></div><span className={`engine-status ${hasResult ? 'ready' : 'pending'}`}>{hasResult ? '✓ ' + t('workspace.ready') : '↻ ' + t('workspace.pending')}</span></div>
    <div className="project-snapshot"><div><small>{t('field.projectName')}</small><strong>{project.project_name}</strong></div><div><small>{t('field.client')}</small><strong>{project.client || '—'}</strong></div><div><small>{t('field.location')}</small><strong>{project.location || '—'}</strong></div><div><small>{t('editor.tube')}</small><strong>{String(config.tube_id || 'T1')}</strong></div></div>
    <div className="overview-layout"><section className="overview-main"><div className="section-lead"><div><span className="eyebrow">01</span><h3>{t('workspace.definition')}</h3></div><button className="text-action" onClick={() => onNavigate('tunnel')}>{t('workspace.openSection')} →</button></div><div className="overview-metrics"><MetricTile label={t('field.length')} value={numberValue(config.length_m).toFixed(0)} unit="m"/><MetricTile label={t('field.width')} value={numberValue(config.width_m).toFixed(1)} unit="m"/><MetricTile label={t('field.height')} value={numberValue(config.height_m).toFixed(1)} unit="m"/><MetricTile label={t('field.speed')} value={numberValue(config.speed_kmh).toFixed(0)} unit="km/h"/></div><div className="overview-route"><div className="route-line"><span className="route-node">A</span><span className="route-segment"/><span className="route-node">B</span></div><div className="route-labels"><span>{String(config.portal_orientation || 'S')}</span><strong>{numberValue(config.length_m).toFixed(0)} m · {config.traffic_direction === 'two_way' ? t('option.twoWay') : t('option.oneWay')}</strong><span>{oppositeOrientation[String(config.portal_orientation)] || 'N'}</span></div></div></section><aside className="overview-action-card"><span className="overview-action-icon">✦</span><strong>{hasResult ? t('workspace.resultAvailable') : t('workspace.calculateNext')}</strong><p>{hasResult ? t('workspace.resultAvailableHint') : t('workspace.calculateNextHint')}</p><button className="primary" onClick={() => onNavigate(hasResult ? 'zones' : 'tunnel')}>{hasResult ? t('step.zones') : t('step.tunnel')} →</button></aside></div>
    {hasResult && <section className="overview-results"><div className="section-lead"><div><span className="eyebrow">02</span><h3>{t('workspace.lastCalculation')}</h3></div><button className="text-action" onClick={() => onNavigate('zones')}>{t('workspace.openSection')} →</button></div><div className="overview-metrics"><MetricTile label="Lth" value={numberValue(summary.Lth).toFixed(1)} unit="cd/m²"/><MetricTile label="Lin" value={numberValue(summary.Lin).toFixed(1)} unit="cd/m²"/><MetricTile label="SD" value={numberValue(summary.SD_m).toFixed(1)} unit="m"/><MetricTile label={t('result.status')} value={t('result.calculated')}/></div></section>}
  </div>;
}

function ZoneTimeline({ result, t }: { result: Record<string, unknown> | null; t: (key: string) => string }) {
  const zones = record(result?.zones);
  const entries = Object.entries(zones).map(([key, value]) => { const zone = record(value); return { key, name: String(zone.zone_name || t(`zone.${key}`)), start: numberValue(zone.s_start), end: numberValue(zone.s_end) }; }).filter(item => Number.isFinite(item.start) && Number.isFinite(item.end) && item.end > item.start).sort((a, b) => a.start - b.start);
  const length = Math.max(1, numberValue(record(result?.summary).length_m, Math.max(...entries.map(item => item.end), 1)));
  return <section className="zone-timeline-card"><div className="section-lead"><div><span className="eyebrow">CIE 88:2004</span><h3>{t('workspace.zoneSequence')}</h3></div><span className="timeline-range">0 m — {length.toFixed(0)} m</span></div>{entries.length ? <><div className="timeline-track">{entries.map(item => <div key={item.key} className={`timeline-zone zone-${item.key}`} style={{ left: `${Math.max(0, item.start / length * 100)}%`, width: `${Math.max(2, Math.min(100, (item.end - item.start) / length * 100))}%` }}><strong>{item.name}</strong><small>{(item.end - item.start).toFixed(0)} m</small></div>)}</div><div className="timeline-axis"><span>{t('workspace.entry')}</span><span>{t('workspace.exit')}</span></div></> : <div className="empty-results">{t('workspace.noZones')}</div>}</section>;
}

function TunnelWorkspace({ config, result, validation, technicalView, onTechnicalViewChange, t }: { config: TunnelConfig; result: Record<string, unknown> | null; validation: ValidationState | null; technicalView: TechnicalView; onTechnicalViewChange: (view: TechnicalView) => void; t: (key: string, params?: Record<string, string | number>) => string }) {
  const calculated = result?.success === true;
  return <div className="workspace-stack phase-workspace">
    <div className="workspace-board phase-shell tunnel-phase-shell">
      <div className="board-heading"><div><span className="eyebrow">01 · CIE 88:2004</span><h2>{t('step.tunnel')}</h2><p>{t('workspace.tunnelHint')}</p></div><span className={`engine-status ${calculated ? 'ready' : 'pending'}`}>{calculated ? `✓ ${t('workflow.calculated')}` : `↻ ${t('workflow.pending')}`}</span></div>
      <div className="phase-guidance"><span className="phase-guidance-number">1</span><div><strong>{t('workspace.tunnelGuidanceTitle')}</strong><p>{t('workspace.tunnelGuidance')}</p></div></div>
       <TunnelTechnicalViewport config={config} result={result} view={technicalView} onViewChange={onTechnicalViewChange}/>
       {validation && <div className={`phase-validation ${validation.valid ? 'valid' : 'invalid'}`}><strong>{validation.valid ? t('validation.ready') : t('validation.attention')}</strong>{validation.errors.length > 0 && <ul>{validation.errors.map(item => <li key={item}>{item}</li>)}</ul>}{validation.warnings.length > 0 && <ul className="warnings">{validation.warnings.map(item => <li key={item}>{item}</li>)}</ul>}</div>}
    </div>
  </div>;
}

function ZoneProfileChart({ points, zones, length, lth, lin, t }: { points: Record<string, unknown>[]; zones: { key: string; zone: Record<string, unknown> }[]; length: number; lth: number; lin: number; t: (key: string) => string }) {
  const chartPoints = points.filter(point => Number.isFinite(Number(point.s)) && Number.isFinite(Number(point.L))).sort((a, b) => numberValue(a.s) - numberValue(b.s));
  const chartLength = Math.max(1, length);
  const yMin = 1;
  const yMax = Math.max(1000, ...chartPoints.map(point => numberValue(point.L) * 1.15));
  const plot = { left: 58, right: 944, top: 18, bottom: 238 };
  const x = (s: number) => plot.left + Math.max(0, Math.min(chartLength, s)) / chartLength * (plot.right - plot.left);
  const y = (value: number) => plot.bottom - (Math.log10(Math.max(yMin, Math.min(yMax, value))) - Math.log10(yMin)) / (Math.log10(yMax) - Math.log10(yMin)) * (plot.bottom - plot.top);
  const ticks = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000].filter(value => value <= yMax * 1.001);
  const path = chartPoints.map((point, index) => `${index ? 'L' : 'M'} ${x(numberValue(point.s)).toFixed(1)} ${y(numberValue(point.L)).toFixed(1)}`).join(' ');
  const bandColors: Record<string, string> = { access: '#fcebea', threshold: '#fff8df', transition: '#e7f5f2', interior: '#e6f5eb', exit: '#f1eaf8', parting: '#fcebea' };
  const bandBorders: Record<string, string> = { access: '#d8a7a3', threshold: '#d79019', transition: '#4b9b89', interior: '#2a9b5f', exit: '#8760a0', parting: '#d8a7a3' };
  return <div className="profile-chart-wrap" role="img" aria-label={t('workspace.longitudinalProfile')}>
    {chartPoints.length ? <><svg className="profile-chart" viewBox="0 0 960 270" preserveAspectRatio="none" aria-hidden="true"><rect x={plot.left} y={plot.top} width={plot.right - plot.left} height={plot.bottom - plot.top} fill="#fffdf9" />{zones.map(({ key, zone }) => { const start = Math.max(0, numberValue(zone.s_start)); const end = Math.min(chartLength, numberValue(zone.s_end)); return end > start ? <rect key={key} x={x(start)} y={plot.top} width={Math.max(1, x(end) - x(start))} height={plot.bottom - plot.top} fill={bandColors[key] || '#f5f2ee'} /> : null; })}{ticks.map(value => <g key={value}><line x1={plot.left} x2={plot.right} y1={y(value)} y2={y(value)} stroke="#ddd6cc" strokeDasharray="3 4" /><text x={plot.left - 8} y={y(value) + 3} textAnchor="end" fill="#766f66" fontSize="10">{value}</text></g>)}{[0, .25, .5, .75, 1].map(ratio => <g key={ratio}><line x1={x(chartLength * ratio)} x2={x(chartLength * ratio)} y1={plot.top} y2={plot.bottom} stroke="#e5ded4" strokeDasharray="3 4" /><text x={x(chartLength * ratio)} y={plot.bottom + 18} textAnchor="middle" fill="#766f66" fontSize="10">{Math.round(chartLength * ratio)} m</text></g>)}{lth > yMin && lth <= yMax && <line x1={plot.left} x2={plot.right} y1={y(lth)} y2={y(lth)} stroke="#e58d00" strokeWidth="2" strokeDasharray="6 4" />}{lin > yMin && lin <= yMax && <line x1={plot.left} x2={plot.right} y1={y(lin)} y2={y(lin)} stroke="#16834f" strokeWidth="2" />}{path && <path d={path} fill="none" stroke="#263238" strokeWidth="2.5" vectorEffect="non-scaling-stroke" />}</svg><div className="profile-axis-label">L (cd/m²) · escala logarítmica</div><div className="profile-zones-legend">{zones.filter(({ zone }) => numberValue(zone.length) > 0).map(({ key, zone }) => <span key={key} style={{ borderColor: bandBorders[key] || '#b8b0a6', background: bandColors[key] || '#f5f2ee' }}><strong>{String(zone.zone_name || t(`zone.${key}`))}</strong><small>{formatNumber(zone.length, 0)} m</small></span>)}</div><div className="profile-line-legend"><span><i className="line-swatch line-lth" />Lth {formatNumber(lth, 2)} cd/m²</span><span><i className="line-swatch line-lin" />Lin {formatNumber(lin, 2)} cd/m²</span></div></> : <div className="empty-results">{t('workspace.profileUnavailable')}</div>}
  </div>;
}

function ZonesWorkspace({ config, result, onOpenLuminaires, t }: { config: TunnelConfig; result: Record<string, unknown> | null; onOpenLuminaires: () => void; t: (key: string, params?: Record<string, string | number>) => string }) {
  const summary = record(result?.summary); const classification = record(result?.classification); const quality = record(result?.quality_criteria); const speed = record(result?.speed); const lthResult = record(result?.lth); const validation = record(result?.validation); const overrides = record(result?.project_overrides);
  const zones = Object.entries(record(result?.zones)).map(([key, value]) => ({ key, zone: record(value) })).sort((a, b) => numberValue(a.zone.s_start) - numberValue(b.zone.s_start));
  const chart = record(result?.chart); const chartData = Array.isArray(chart.data) ? chart.data.map(value => record(value)) : []; const warnings = Array.isArray(result?.warnings) ? result.warnings.map(String) : []; const isBidirectional = String(config.traffic_direction || '') === 'two_way';
  if (!result?.success) return <div className="workspace-board phase-locked"><div className="empty-results">{t('workspace.zonesLocked')}</div></div>;
  const validationIsValid = validation.valid !== false;
  return <div className="workspace-stack phase-workspace">
    <div className="workspace-board phase-shell zones-board">
      <div className="board-heading"><div><span className="eyebrow">02 · CIE 88:2004</span><h2>{t('step.zones')}</h2><p>{t('workspace.zonesHint')}</p></div><span className="engine-status ready">✓ {t('workflow.calculated')}</span></div>
      <div className="zone-alerts">{warnings.map((warning, index) => <div className="zone-alert zone-alert-warning" key={`${warning}-${index}`}>⚠ {warning}</div>)}{validationIsValid && !overrides.has_overrides && <div className="zone-alert zone-alert-success">✓ Perfil longitudinal válido según CIE 88:2004</div>}{overrides.has_overrides && <div className="zone-alert zone-alert-warning">⚠ {String(overrides.note || 'Valores de proyecto aplicados; deben verificarse frente a CIE/OC 36.')}</div>}</div>
      <div className="zones-summary-kpis kpi-grid"><Kpi label={t('field.speed')} value={formatNumber(summary.speed_kmh, 0)} unit="km/h"/><Kpi label={t('result.lin')} value={formatNumber(summary.Lin, 2)} unit="cd/m²"/><Kpi label="L noche normal" value={formatNumber(summary.L_night_normal ?? summary.Lin, 2)} unit="cd/m²"/><Kpi label="L noche reducida" value={formatNumber(summary.L_night_reduced ?? summary.L_night, 2)} unit="cd/m²"/><Kpi label={t('field.tunnelClass')} value={formatNumber(lthResult.tunnel_class, 0)}/><Kpi label="k_Lth" value={formatNumber(summary.k_factor, 2)} unit="Lth/L20"/>{lthResult.qc_used && <Kpi label="q_c" value={formatNumber(summary.qc, 2)} unit="L/Ev"/>}</div>
      <div className={`portal-results-grid ${isBidirectional ? 'is-bidirectional' : ''}`}><div className="portal-result-group"><div className="portal-result-label">← PORTAL A</div><div className="portal-result-kpis kpi-grid"><Kpi label="SD" value={formatNumber(summary.SD_m, 1)} unit="m"/><Kpi label="L₂₀" value={formatNumber(summary.L20, 0)} unit="cd/m²"/><Kpi label="Lth" value={formatNumber(lthResult.Lth ?? summary.Lth, 2)} unit="cd/m²"/></div></div>{isBidirectional && <div className="portal-result-group"><div className="portal-result-label portal-b-label">PORTAL B →</div><div className="portal-result-kpis kpi-grid"><Kpi label="SD" value={formatNumber(lthResult.SD_b_m ?? summary.SD_m, 1)} unit="m"/><Kpi label="L₂₀" value={formatNumber(lthResult.L20_b ?? summary.L20, 0)} unit="cd/m²"/><Kpi label="Lth" value={formatNumber(lthResult.Lth_b ?? summary.Lth, 2)} unit="cd/m²"/></div></div>}</div>
      <div className="phase-result-header"><div><strong>{t('workspace.cieResultReady')}</strong><p>{t('workspace.cieResultReadyHint')}</p></div><button type="button" className="primary" onClick={onOpenLuminaires}>{t('workspace.openLuminaires')} →</button></div>
      <section className="zone-chart-section"><div className="section-lead"><div><span className="eyebrow">CIE 88:2004</span><h3>{t('workspace.longitudinalProfile')}</h3></div><span className="detail-muted">{chartData.length} puntos</span></div><ZoneProfileChart points={chartData} zones={zones} length={numberValue(summary.length_m)} lth={numberValue(summary.Lth)} lin={numberValue(summary.Lin)} t={t}/></section>
    </div>
    <section className="workspace-board classification-card"><div className="section-lead"><div><span className="eyebrow">OC 36 · CIE 88</span><h3>{t('workspace.classification')}</h3></div><span className="status-pill ready">OC 36 · clase {formatNumber(lthResult.tunnel_class, 0)}</span></div><div className="classification-badges"><span className="class-badge">OC 36 · clase {formatNumber(lthResult.tunnel_class, 0)}</span><span className={`class-badge ${classification.optical === 'optically_long' ? 'class-long' : 'class-short'}`}>{classification.optical === 'optically_long' ? '🔴 Largo' : '🟢 Corto'}</span><span className="class-badge">Ilum: {String(classification.daylighting || '—')}</span><span className="classification-geometric">{String(classification.geometric || '—')}</span></div><p className="classification-copy">{String(classification.justification || '')}</p><p className="traceability-line">L20: <strong>{String(lthResult.L20_source || '—')}</strong> · DP: <strong>{String(lthResult.SD_source || '—')}</strong> · k_Lth: <strong>{String(lthResult.k_source || '—')}</strong> · q_c: <strong>{lthResult.qc_used ? 'utilizado' : 'no interviene'}</strong> · {String(lthResult.standard || '')}</p></section>
    <section className="workspace-board zones-table-card"><div className="section-lead"><div><span className="eyebrow">CIE 88:2004</span><h3>{t('section.normativeZones')}</h3></div><span className="status-pill ready">{zones.length}</span></div><div className="table-wrap zone-table-wrap"><table><thead><tr><th>{t('result.zone')}</th><th>{t('result.start')} (m)</th><th>{t('result.end')} (m)</th><th>{t('result.length')} (m)</th><th>L inicio</th><th>L fin</th><th>{t('result.required')}</th></tr></thead><tbody>{zones.map(({ key, zone }) => <tr className={`zone-row zone-row-${key}`} key={key}><td><span className="zone-name-badge"><strong>{String(zone.zone_name || t(`zone.${key}`))}</strong></span></td><td>{formatNumber(zone.s_start)} </td><td>{formatNumber(zone.s_end)} </td><td><strong>{formatNumber(zone.length)}</strong></td><td>{formatNumber(zone.L_start, 2)}</td><td>{formatNumber(zone.L_end, 2)}</td><td><strong>{formatNumber(zone.L_min_required ?? zone.L_required, 2)}</strong></td></tr>)}</tbody></table></div></section>
    <section className="workspace-board quality-card"><div className="section-lead"><div><span className="eyebrow">CIE 88:2004</span><h3>✅ Criterios de Calidad CIE 88</h3></div><span className="status-pill ready">{validationIsValid ? t('workspace.compliant') : t('workspace.reviewRequired')}</span></div><div className="quality-note">U₀, Uₗ, TI y ratio paredes requieren cálculo fotométrico completo con LDT.</div><div className="table-wrap"><table className="quality-table"><thead><tr><th>CRITERIO</th><th>NORMA</th><th>ESTADO</th></tr></thead><tbody><tr><td>Uniformidad U₀</td><td>≥ {formatNumber(quality.Uo_min, 2)}</td><td>Requiere LDT</td></tr><tr><td>Uniformidad Uₗ</td><td>≥ {formatNumber(quality.Ul_min, 2)}</td><td>Requiere LDT</td></tr><tr><td>Deslumbramiento TI</td><td>≤ {formatNumber(quality.TI_max, 0)} %</td><td>Requiere LDT</td></tr><tr><td>Ratio pared/calzada</td><td>≥ {formatNumber(quality.wall_ratio_min, 2)}</td><td>Requiere LDT</td></tr><tr><td>Perfil longitudinal</td><td>CIE 88:2004</td><td className="quality-ok">✅ {t('workspace.compliant')}</td></tr></tbody></table></div><p className="detail-note">{String(quality.note || t('result.note'))}</p></section>
  </div>;
}

function LuminaireResultSummary({ luminaires, t }: { luminaires: Record<string, unknown>; t: (key: string, params?: Record<string, string | number>) => string }) {
  const lum = record(luminaires.luminaires);
  const photometric = record(luminaires.photometric);
  const totals = record(lum.totals);
  const zones = Array.isArray(lum.zones) ? lum.zones.map(record) : [];
  const scenarioData = record(photometric.scenarios);
  const scenarioKeys = ['sunny', 'normal', 'overcast', 'dusk', 'night', 'night_reduced', 'night_normal'];
  const scenarioNames: Record<string, string> = { sunny: 'Soleado', normal: 'Normal', overcast: 'Cubierto', dusk: 'Crepuscular', night: 'Noche reducida', night_reduced: 'Noche reducida', night_normal: 'Noche normal' };
  const profile = record(photometric.real_profile);
  const points = Array.isArray(profile.points) ? profile.points.map(record).filter(point => Number.isFinite(Number(point.L))) : [];
  const maxL = Math.max(1, ...points.map(point => numberValue(point.L)));
  const sampled = points.filter((_, index) => index % Math.max(1, Math.ceil(points.length / 48)) === 0 || index === points.length - 1);
  return <section className="photometric-result-card"><div className="result-card-heading"><div><span className="eyebrow">CIE 140:2019</span><h3>{t('workspace.photometricResult')}</h3><p>{photometric.verification_source ? String(photometric.verification_source) : t('workspace.photometricResultHint')}</p></div><span className={`status-pill ${photometric.overall_compliant ? 'ready' : 'warning'}`}>{photometric.overall_compliant ? t('workspace.compliant') : t('workspace.reviewRequired')}</span></div>
    <div className="kpi-grid photometric-kpis"><Kpi label={t('workspace.totalLuminaires')} value={formatNumber(totals.n_luminaires, 0)} /><Kpi label={t('workspace.positions')} value={formatNumber(totals.n_positions, 0)} /><Kpi label={t('workspace.installedPower')} value={formatNumber(totals.installed_power_kw, 2)} unit="kW" /><Kpi label={t('workspace.powerDensity')} value={formatNumber(totals.power_density_wm2, 2)} unit="W/m²" /></div>
    <SectionTitle title={t('workspace.zoneDesign')} /><div className="table-wrap"><table><thead><tr><th>{t('result.zone')}</th><th>{t('workspace.positions')}</th><th>{t('workspace.spacing')}</th><th>{t('workspace.modelOptic')}</th><th>{t('workspace.current')}</th><th>{t('workspace.power')}</th><th>L/Lreq</th><th>U₀</th><th>Uₗ</th></tr></thead><tbody>{zones.map((zone, index) => { const setpoints = Array.isArray(zone.setpoints) ? zone.setpoints.map(record) : []; const first = setpoints[0]; const last = setpoints[setpoints.length - 1]; const positionText = setpoints.length ? `${setpoints.length} · ${numberValue(first?.s).toFixed(1)}–${numberValue(last?.s).toFixed(1)} m` : `${numberValue(zone.n_positions, 0)}`; return <tr key={`${String(zone.zone_name || zone.zone_type)}-${index}`}><td><strong>{String(zone.zone_name || zone.zone_type || '—')}</strong></td><td>{positionText}</td><td>{formatNumber(zone.d_used)} m</td><td>{String(zone.model || '—')} · {String(zone.optic || '—')}</td><td>{formatNumber(zone.current_mA, 0)} mA</td><td>{formatNumber(zone.power_w, 1)} W</td><td>{formatNumber(numberValue(zone.L_estimated) / Math.max(.01, numberValue(zone.L_required)), 2)}</td><td>{formatNumber(zone.U0, 2)}</td><td>{formatNumber(zone.Ul, 2)}</td></tr>; })}</tbody></table></div>
    <SectionTitle title={t('workspace.scenes')} /><div className="scene-results-grid">{scenarioKeys.filter(key => scenarioData[key]).map(key => { const scene = record(scenarioData[key]); const state = record(scene.photometric || scene); return <article className="scene-result" key={key}><div><strong>{String(record(lum.scenarios && record(lum.scenarios)[key]).name || scenarioNames[key])}</strong><span>{scene.active_luminaires != null ? `${numberValue(scene.active_luminaires, 0)} ${t('workspace.active')}` : ''}</span></div><dl><div><dt>L/Lreq</dt><dd>{formatNumber(state.minimum_L_ratio, 2)}</dd></div><div><dt>U₀</dt><dd>{formatNumber(state.minimum_U0, 2)}</dd></div><div><dt>Uₗ</dt><dd>{formatNumber(state.minimum_Ul, 2)}</dd></div><div><dt>TI</dt><dd>{formatNumber(state.maximum_TI_pct, 1)}%</dd></div></dl><span className={`scene-status ${state.compliant === false ? 'warning' : 'ready'}`}>{state.compliant === false ? t('workspace.reviewRequired') : t('workspace.compliant')}</span></article>; })}</div>
    {sampled.length > 0 && <><SectionTitle title={t('workspace.photometricProfile')} /><div className="cie-profile-chart photometric-profile-chart" role="img" aria-label={t('workspace.photometricProfile')}>{sampled.map((point, index) => <span key={`${point.s}-${index}`} className="profile-bar profile-photometric" title={`${Number(point.s || 0).toFixed(1)} m · L ${Number(point.L).toFixed(2)} cd/m²`} style={{ height: `${Math.max(8, numberValue(point.L) / maxL * 100)}%` }} />)}</div></>}
  </section>;
}

function LuminaireCrossSection({ config, t }: { config: TunnelConfig; t: (key: string, params?: Record<string, string | number>) => string }) {
  const lum = record(config.lum_config);
  const width = Math.max(1, numberValue(config.width_m, 10.5));
  const height = Math.max(1, numberValue(config.height_m, 5.5));
  const lanes = Math.max(1, Math.round(numberValue(config.num_lanes, 2)));
  const laneWidth = Math.max(1, numberValue(config.lane_width_m, width / lanes));
  const leftReserve = Math.max(0, numberValue(config.sidewalk_left_m)) + Math.max(0, numberValue(config.shoulder_left_m));
  const rightReserve = Math.max(0, numberValue(config.sidewalk_right_m)) + Math.max(0, numberValue(config.shoulder_right_m));
  const roadWidth = Math.max(1, width - leftReserve - rightReserve);
  const mountingHeight = Math.max(0.5, Math.min(height - 0.15, numberValue(lum.mounting_height_m, 4.5)));
  const wallOffset = Math.max(0, numberValue(lum.wall_offset_m, 0.3));
  const arrangement = String(lum.arrangement || 'bilateral_sym');
  const optic = String(lum.optic || 'F151');
  const scale = Math.min(54, 700 / width, 286 / height);
  const roadX = 450 - roadWidth * scale / 2;
  const roadRight = roadX + roadWidth * scale;
  const baseY = 390;
  const tunnelHeight = height * scale;
  const tunnelTop = baseY - tunnelHeight;
  const roof = String(config.tunnel_shape) === 'rectangular'
    ? `M ${roadX} ${tunnelTop} H ${roadRight} V ${baseY} H ${roadX} Z`
    : String(config.tunnel_shape) === 'circular'
      ? `M ${roadX} ${baseY} A ${roadWidth * scale / 2} ${tunnelHeight} 0 0 1 ${roadRight} ${baseY} Z`
      : `M ${roadX} ${baseY} V ${baseY - tunnelHeight * .52} Q 450 ${tunnelTop - tunnelHeight * .08} ${roadRight} ${baseY - tunnelHeight * .52} V ${baseY} Z`;
  const luminaireY = Math.max(tunnelTop + 24, baseY - mountingHeight * scale);
  const innerOffset = Math.min(roadWidth * .1, Math.max(.2, wallOffset));
  const centerOffset = Math.min(roadWidth * .18, Math.max(.7, roadWidth / Math.max(4, lanes * 2)));
  const leftLuminaireX = roadX + innerOffset * scale;
  const rightLuminaireX = roadRight - innerOffset * scale;
  const centerX = (roadX + roadRight) / 2;
  const points = arrangement === 'central_single'
    ? [{ x: centerX, side: 'central' }]
    : arrangement === 'central_double'
      ? [{ x: centerX - centerOffset * scale, side: 'central' }, { x: centerX + centerOffset * scale, side: 'central' }]
      : arrangement === 'lateral_left'
        ? [{ x: leftLuminaireX, side: 'left' }]
        : arrangement === 'lateral_right'
          ? [{ x: rightLuminaireX, side: 'right' }]
          : [{ x: leftLuminaireX, side: 'left' }, { x: rightLuminaireX, side: 'right' }];
  const shapeLabel = String(config.tunnel_shape) === 'rectangular' ? t('preview.rectangular') : String(config.tunnel_shape) === 'circular' ? t('preview.circular') : t('preview.horseshoe');
  const roadY = baseY + 13;
  const shoulderLeftWidth = leftReserve * scale;
  const shoulderRightWidth = rightReserve * scale;
  return <div className="luminaire-cross-section-wrap">
    <svg className="luminaire-cross-section" viewBox="0 0 900 500" role="img" aria-label={t('workspace.luminaireVisualAria')}>
      <defs>
        <linearGradient id="luminaireTunnelFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#26354c"/><stop offset="1" stopColor="#1b273b"/></linearGradient>
        <linearGradient id="luminaireRoadFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#39475b"/><stop offset="1" stopColor="#202c40"/></linearGradient>
      </defs>
      <rect x="20" y="20" width="860" height="455" rx="14" fill="#0d1629" />
      <text x="45" y="54" className="luminaire-svg-kicker">{t('workspace.luminaireVisualTitle')}</text>
      <text x="855" y="54" textAnchor="end" className="luminaire-svg-muted">{shapeLabel}</text>
      <path d={roof} fill="url(#luminaireTunnelFill)" stroke="#52647f" strokeWidth="4" />
      {leftReserve > 0 && <rect x={roadX - shoulderLeftWidth} y={baseY - 2} width={shoulderLeftWidth} height="19" fill="#596579" />}
      {rightReserve > 0 && <rect x={roadRight} y={baseY - 2} width={shoulderRightWidth} height="19" fill="#596579" />}
      <rect x={roadX} y={baseY - 2} width={roadWidth * scale} height="19" fill="url(#luminaireRoadFill)" />
      {Array.from({ length: lanes + 1 }).map((_, index) => <line key={`lane-${index}`} x1={roadX + roadWidth * scale * index / lanes} y1={baseY + 1} x2={roadX + roadWidth * scale * index / lanes} y2={roadY + 13} stroke={index === 0 || index === lanes ? '#c8d1dc' : '#c9a227'} strokeWidth={index === 0 || index === lanes ? 2 : 1.5} strokeDasharray={index === 0 || index === lanes ? undefined : '7 6'} />)}
      <line x1={roadX - 30} y1={baseY} x2={roadX - 30} y2={tunnelTop} className="luminaire-dimension-line" />
      <line x1={roadX - 39} y1={tunnelTop} x2={roadX - 21} y2={tunnelTop} className="luminaire-dimension-cap" />
      <line x1={roadX - 39} y1={baseY} x2={roadX - 21} y2={baseY} className="luminaire-dimension-cap" />
      <text x={roadX - 42} y={(tunnelTop + baseY) / 2} textAnchor="end" className="luminaire-dimension-text">H = {height.toFixed(2)} m</text>
      <line x1={roadX} y1="443" x2={roadRight} y2="443" className="luminaire-dimension-line" />
      <line x1={roadX} y1="435" x2={roadX} y2="451" className="luminaire-dimension-cap" />
      <line x1={roadRight} y1="435" x2={roadRight} y2="451" className="luminaire-dimension-cap" />
      <text x="450" y="468" textAnchor="middle" className="luminaire-dimension-text">W = {width.toFixed(2)} m</text>
      <text x="450" y={Math.max(76, tunnelTop + 25)} textAnchor="middle" className="luminaire-svg-title">{t('workspace.luminaireSectionShape', { shape: shapeLabel })}</text>
      {points.map((point, index) => <g key={`${point.side}-${index}`} className="luminaire-marker-group">
        <line x1={point.x} y1={luminaireY + 8} x2={point.x} y2={baseY - 3} className="luminaire-drop-line" />
        <rect x={point.x - 13} y={luminaireY - 7} width="26" height="10" rx="4" fill="#f4bd29" stroke="#fff1a8" strokeWidth="2" />
        <circle cx={point.x} cy={luminaireY - 2} r="3" fill="#fff8d1" />
        <text x={point.x} y={luminaireY - 18} textAnchor="middle" className="luminaire-marker-label">{optic}</text>
      </g>)}
      <text x={roadX + 10} y={baseY - 23} className="luminaire-svg-muted">{t('workspace.luminaireMountingSvg', { value: mountingHeight.toFixed(2) })}</text>
    </svg>
  </div>;
}

function LuminairePlacementPlan({ zones, length, calculated, t }: { zones: unknown[]; length: number; calculated: boolean; t: (key: string, params?: Record<string, string | number>) => string }) {
  const normalized = zones.map(record).map((zone, index) => {
    const setpoints = Array.isArray(zone.setpoints) ? zone.setpoints.map(record) : [];
    const first = setpoints[0];
    const last = setpoints[setpoints.length - 1];
    const start = numberValue(zone.s_start ?? zone.start_m ?? first?.s, 0);
    const end = numberValue(zone.s_end ?? zone.end_m ?? last?.s, length);
    const count = numberValue(zone.n_luminaires ?? zone.n_positions ?? setpoints.length, 0);
    return { zone, index, start: Math.min(start, end), end: Math.max(start, end), count };
  });
  const rangeStart = Math.min(0, ...normalized.map(item => item.start));
  const rangeEnd = Math.max(length, ...normalized.map(item => item.end));
  const range = Math.max(1, rangeEnd - rangeStart);
  return <section className="luminaire-placement-board">
    <div className="section-lead"><div><span className="eyebrow">CIE 140:2019</span><h3>{t('workspace.luminairePlacementTitle')}</h3></div><span className={`status-pill ${calculated ? 'ready' : ''}`}>{calculated ? t('workspace.luminairePlacementReady') : t('workspace.luminairePlacementPending')}</span></div>
    <p className="luminaire-placement-hint">{calculated ? t('workspace.luminairePlacementHint') : t('workspace.luminairePlacementEmpty')}</p>
    {calculated && normalized.length > 0 && <>
      <div className="luminaire-placement-track" aria-label={t('workspace.luminairePlacementTitle')}>
        {normalized.map(item => <div key={`${String(item.zone.zone_name || item.zone.zone_type || 'zone')}-${item.index}`} className={`luminaire-placement-zone zone-${item.index % 5}`} style={{ left: `${(item.start - rangeStart) / range * 100}%`, width: `${Math.max(2, (item.end - item.start) / range * 100)}%` }}><strong>{String(item.zone.zone_name || item.zone.zone_type || '—')}</strong><small>{item.count} · {Math.max(0, item.end - item.start).toFixed(1)} m</small></div>)}
      </div>
      <div className="luminaire-placement-axis"><span>{rangeStart.toFixed(0)} m</span><span>{(rangeStart + range * .25).toFixed(0)} m</span><span>{(rangeStart + range * .5).toFixed(0)} m</span><span>{(rangeStart + range * .75).toFixed(0)} m</span><span>{rangeEnd.toFixed(0)} m</span></div>
    </>}
  </section>;
}

function LuminaireZoneOverrides({ zones, config, onChange, t }: { zones: unknown[]; config: TunnelConfig; onChange: (key: string, value: unknown) => void; t: (key: string, params?: Record<string, string | number>) => string }) {
  const tilts = record(config.tilt_overrides);
  const tandems = record(config.tandem_overrides);
  const updateTilt = (name: string, value: string) => onChange('tilt_overrides', { ...tilts, [name]: value === '' ? null : Number(value) });
  const updateTandem = (name: string, value: boolean) => onChange('tandem_overrides', { ...tandems, [name]: value });
  return <section className="workspace-board luminaire-overrides"><SectionTitle title={t('section.luminaireOverrides')} /><p className="luminaire-section-note">{t('luminaire.overridesHint')}</p><div className="table-wrap"><table><thead><tr><th>{t('result.zone')}</th><th>{t('field.zoneTilt')}</th><th>{t('field.tandem')}</th></tr></thead><tbody>{zones.map((item, index) => { const zone = record(item); const name = String(zone.zone_name || zone.zone_type || `zone_${index + 1}`); return <tr key={`${name}-${index}`}><td><strong>{name}</strong></td><td><input className="table-input" type="number" min={-45} max={45} step={1} value={tilts[name] == null ? '' : String(tilts[name])} placeholder="Auto" onChange={event => updateTilt(name, event.target.value)} /></td><td><input type="checkbox" checked={Boolean(tandems[name])} onChange={event => updateTandem(name, event.target.checked)} /></td></tr>; })}</tbody></table></div></section>;
}

function LuminaireWorkspace({ config, result, luminaires, onCalculated, onChange, onConfigChange, busy, setBusy, setError, t }: { config: TunnelConfig; result: Record<string, unknown> | null; luminaires: Record<string, unknown> | null; onCalculated: (data: Record<string, unknown>) => void; onChange: (key: string, value: unknown) => void; onConfigChange: (key: string, value: unknown) => void; busy: boolean; setBusy: (value: boolean) => void; setError: (value: string) => void; t: (key: string, params?: Record<string, string | number>) => string }) {
  const lum = record(luminaires?.luminaires);
  const zones = Array.isArray(lum.zones) ? lum.zones : [];
  const totals = record(lum.totals);
  const totalLuminaires = numberValue(totals.n_luminaires) || zones.reduce((sum, item) => sum + numberValue(record(item).n_luminaires || record(item).total_luminaires || record(item).luminaire_count), 0);
  const length = numberValue(record(result?.summary).length_m, numberValue(config.length_m, 300));
  const run = async () => { setBusy(true); setError(''); try { const data = await calculateLuminaires(config); if (data.success === false) throw new Error(String(data.error || t('editor.calculationFailed'))); onCalculated(data); } catch (err) { setError(err instanceof Error ? err.message : t('editor.calculationFailed')); } finally { setBusy(false); } };
  return <div className="workspace-stack phase-workspace"><div className="workspace-board phase-shell"><div className="board-heading"><div><span className="eyebrow">03 · CIE 140:2019</span><h2>{t('step.luminaires')}</h2><p>{t('workspace.luminairesHint')}</p></div><button className="primary" onClick={() => void run()} disabled={busy || !result?.success}>{busy ? t('workspace.calculating') : t('workspace.runLuminaire')}</button></div><div className="phase-guidance"><span className="phase-guidance-number">3</span><div><strong>{t('workspace.luminairesGuidanceTitle')}</strong><p>{t('workspace.luminairesGuidance')}</p></div></div><div className="parameter-note luminaire-scope-note"><span className="parameter-note-icon">i</span><div><strong>{t('field.luminanceGrid')}</strong><p>{t('field.luminanceGridNote')}</p></div></div><div className="luminaire-phase-grid"><div className="luminaire-visual-column"><section className="luminaire-visual-board"><div className="section-lead"><div><span className="eyebrow">{t('workspace.luminaireVisualEyebrow')}</span><h3>{t('workspace.luminaireVisualTitle')}</h3></div><span className={`status-pill ${luminaires ? 'ready' : ''}`}>{luminaires ? `${totalLuminaires} ${t('workspace.totalLuminaires').toLowerCase()}` : t('workspace.luminairePreviewPending')}</span></div><LuminaireCrossSection config={config} t={t}/><div className="luminaire-visual-specs"><div><span>{t('workspace.luminaireArrangement')}</span><strong>{String(record(config.lum_config).arrangement || 'bilateral_sym')}</strong></div><div><span>{t('workspace.luminaireMounting')}</span><strong>{numberValue(record(config.lum_config).mounting_height_m, 4.5).toFixed(2)} m</strong></div><div><span>{t('workspace.luminaireOptic')}</span><strong>{String(record(config.lum_config).optic || 'F151')}</strong></div><div><span>{t('workspace.luminaireGeometryWidth')}</span><strong>{numberValue(config.width_m, 10.5).toFixed(2)} m</strong></div></div><p className="luminaire-visual-hint">{t('workspace.luminaireVisualHint')}</p></section><LuminairePlacementPlan zones={zones} length={length} calculated={Boolean(luminaires)} t={t}/></div></div></div>{luminaires && <LuminaireResultSummary luminaires={luminaires} t={t}/>} {luminaires && zones.length > 0 && <LuminaireZoneOverrides zones={zones} config={config} onChange={onConfigChange} t={t}/>}</div>;
}

function ControlSettings({ config, onChange, t }: { config: TunnelConfig; onChange: (key: string, value: unknown) => void; t: (key: string, params?: Record<string, string | number>) => string }) {
  const topology = String(config.control_topology || 'smartec_wirepas');
  return <>
    <div className="form-grid compact-grid">
      <SelectField label={t('field.controlProtocol')} value={String(config.control_protocol || 'DALI')} options={[["DALI", t('option.protocolDali')], ["DALI-continuous", t('option.protocolDali')], ["SmartEC", t('option.protocolSmartec')], ["DALI-scenes", t('option.protocolScenes')], ["0-10V", t('option.protocol010')]]} onChange={value => onChange('control_protocol', value)} />
      <SelectField label={t('field.sensorType')} value={String(config.sensor_type || 'luminancemeter_L20')} options={[["luminancemeter_L20", t('option.sensorL20')], ["photocell_Lad", t('option.sensorLad')], ["schedule", t('option.sensorSchedule')]]} onChange={value => onChange('sensor_type', value)} />
      <SelectField label={t('field.sampleInterval')} value={String(config.sample_interval_min ?? 10)} options={[["5", "5 min"], ["10", "10 min"], ["15", "15 min"], ["30", "30 min"]]} onChange={value => onChange('sample_interval_min', Number(value))} />
      <SelectField label={t('field.rampTime')} value={String(config.ramp_time_s ?? 60)} options={[["30", "30 s"], ["60", "60 s"], ["120", "120 s"], ["300", "300 s"]]} onChange={value => onChange('ramp_time_s', Number(value))} />
    </div>
    <div className="form-grid compact-grid">
      <NumberField label={t('workspace.annualHours')} unit="h" value={config.annual_operation_hours ?? 8760} min={0} max={8784} step={1} onChange={value => onChange('annual_operation_hours', value)} />
      <NumberField label={t('field.nightHours')} unit="h" value={config.night_operation_hours ?? 4300} min={0} max={8784} step={1} onChange={value => onChange('night_operation_hours', value)} />
      <NumberField label={t('field.nightReducedShare')} unit="%" value={config.night_reduced_share_pct ?? 30} min={0} max={100} step={1} onChange={value => onChange('night_reduced_share_pct', value)} />
      <NumberField label={t('field.energyTariff')} unit="€/kWh" value={config.energy_tariff_eur_kwh ?? 0.15} min={0} max={10} step={0.01} onChange={value => onChange('energy_tariff_eur_kwh', value)} />
      <NumberField label={t('field.driverMin')} unit="%" value={Number(config.driver_min_dim_pct ?? 0.1) <= 1 ? Number(config.driver_min_dim_pct ?? 0.1) * 100 : config.driver_min_dim_pct} min={0} max={100} step={1} onChange={value => onChange('driver_min_dim_pct', Number(value) / 100)} />
      <NumberField label={t('field.dimMin')} unit="%" value={config.dim_min_pct ?? 20} min={0} max={100} step={1} onChange={value => onChange('dim_min_pct', value)} />
      <NumberField label={t('field.dimMax')} unit="%" value={config.dim_max_pct ?? 100} min={0} max={100} step={1} onChange={value => onChange('dim_max_pct', value)} />
      <NumberField label={t('field.nightNormalLuminance')} unit="cd/m²" value={config.night_normal_luminance_cd_m2} min={0} max={100} step={0.1} placeholder={t('option.autoPlaceholder')} onChange={value => onChange('night_normal_luminance_cd_m2', value)} />
      <NumberField label={t('field.nightReducedLuminance')} unit="cd/m²" value={config.night_reduced_luminance_cd_m2} min={0} max={100} step={0.1} placeholder={t('option.autoPlaceholder')} onChange={value => onChange('night_reduced_luminance_cd_m2', value)} />
    </div>
    <div className="form-grid compact-grid">
      <SelectField label={t('field.controlTopology')} value={topology} options={[["smartec_wirepas", t('option.topologyWirepas')], ["smartec_dali_wired", t('option.topologyDali')]]} onChange={value => onChange('control_topology', value)} />
      {topology === 'smartec_wirepas' ? <NumberField label={t('field.wirepasNodes')} value={config.wirepas_nodes_per_gateway ?? 200} min={1} max={1000} step={1} onChange={value => onChange('wirepas_nodes_per_gateway', value)} /> : <NumberField label={t('field.daliAddresses')} value={config.dali_max_addresses_per_line ?? 64} min={1} max={64} step={1} onChange={value => onChange('dali_max_addresses_per_line', value)} />}
      <NumberField label={t('field.daliGroupSpan')} unit="m" value={config.dali_group_span_m ?? 60} min={1} max={500} step={1} onChange={value => onChange('dali_group_span_m', value)} />
      <NumberField label={t('field.daliCabinet')} unit="m" value={config.dali_cabinet_position_m ?? 0} min={0} onChange={value => onChange('dali_cabinet_position_m', value)} />
      <NumberField label={t('workspace.transitionGroups')} value={config.n_transition_groups ?? 4} min={1} max={12} step={1} onChange={value => onChange('n_transition_groups', value)} />
      <SelectField label={t('workspace.controlArchitecture')} value={String(config.control_architecture || 'permanent_base_plus_portal_reinforcement')} options={[["permanent_base_plus_portal_reinforcement", t('workspace.controlPermanent')], ["legacy_zonal", t('workspace.controlLegacy')]]} onChange={value => onChange('control_architecture', value)} />
    </div>
  </>;
}

function ControlWorkspace({ config, result, luminaires, control, onCalculated, onChange, onOpenReport, busy, setBusy, setError, t }: { config: TunnelConfig; result: Record<string, unknown> | null; luminaires: Record<string, unknown> | null; control: Record<string, unknown> | null; onCalculated: (data: Record<string, unknown>) => void; onChange: (key: string, value: unknown) => void; onOpenReport: () => void; busy: boolean; setBusy: (value: boolean) => void; setError: (value: string) => void; t: (key: string, params?: Record<string, string | number>) => string }) {
  const plan = record(control?.control); const scenes = Array.isArray(plan.scenes) ? plan.scenes : []; const groups = Array.isArray(plan.groups) ? plan.groups : [];
  const lum = record(luminaires?.luminaires); const totals = record(lum.totals); const photometric = record(luminaires?.photometric); const canRun = result?.success === true && Boolean(luminaires);
  const run = async () => { setBusy(true); setError(''); try { const data = await calculateControl(config); if (data.success === false) throw new Error(String(data.error || t('editor.calculationFailed'))); onCalculated(data); } catch (err) { setError(err instanceof Error ? err.message : t('editor.calculationFailed')); } finally { setBusy(false); } };
  return <div className="workspace-stack phase-workspace">
    <div className="workspace-board phase-shell">
      <div className="board-heading"><div><span className="eyebrow">04 · DALI · SMARTEC</span><h2>{t('step.control')}</h2><p>{t('workspace.controlHint')}</p></div><button className="primary" onClick={() => void run()} disabled={busy || !canRun}>{busy ? t('workspace.calculating') : t('workspace.runControl')}</button></div>
      <div className="phase-guidance"><span className="phase-guidance-number">4</span><div><strong>{t('workspace.controlGuidanceTitle')}</strong><p>{t('workspace.controlGuidance')}</p></div></div>
       {!canRun && <div className="phase-locked"><strong>{t('workspace.controlLocked')}</strong><p>{t('workspace.controlLockedHint')}</p></div>}
      <div className="control-grid"><div className="control-card"><span className="control-icon">◌</span><strong>{control ? t('workspace.controlCalculated') : t('workspace.controlPending')}</strong><p>{t('workspace.controlHint')}</p><div className="overview-metrics"><MetricTile label={t('workspace.scenes')} value={scenes.length || '—'}/><MetricTile label={t('workspace.groups')} value={groups.length || '—'}/><MetricTile label={t('workspace.totalLuminaires')} value={numberValue(totals.n_luminaires, 0) || '—'}/></div></div><div className="control-card"><h3>{t('workspace.photometricInput')}</h3><div className="result-definition-list"><div><dt>{t('workspace.installedPower')}</dt><dd>{formatNumber(totals.installed_power_kw, 2)} kW</dd></div><div><dt>{t('workspace.photometricStatus')}</dt><dd>{photometric.overall_compliant ? t('workspace.compliant') : t('workspace.reviewRequired')}</dd></div></div></div></div>
      {control && <div className="phase-result-header"><div><strong>{t('workspace.controlCalculated')}</strong><p>{t('workspace.controlResultHint')}</p></div><button type="button" className="primary" onClick={onOpenReport}>{t('workspace.openReport')} →</button></div>}
    </div>
     <div className="workspace-board"><div className="section-lead"><div><span className="eyebrow">CIE 140 · ESCENAS</span><h3>{t('workspace.operatingModes')}</h3></div><span className="status-pill ready">{scenes.length || '—'}</span></div>{scenes.length ? <div className="scene-results-grid">{scenes.slice(0, 8).map((scene, index) => { const value = record(scene); const sceneGroupCount = Array.isArray(value.groups) ? value.groups.length : '—'; return <article className="scene-result" key={String(value.name || value.scene || index)}><div><strong>{String(value.name || value.scene || `Scene ${index + 1}`)}</strong><span>{String(value.protocol || value.mode || 'DALI / SMARTEC')}</span></div><dl><div><dt>{t('workspace.groups')}</dt><dd>{String(value.group_count ?? sceneGroupCount)}</dd></div><div><dt>{t('workspace.level')}</dt><dd>{String(value.level ?? value.dimming ?? value.value ?? '—')}</dd></div></dl></article>; })}</div> : <div className="empty-results">{t('workspace.noControl')}</div>}</div>
  </div>;
}

function ReportWorkspace({ config, result, luminaires, control, tubeIds, tubeConfigs, projectName, onChange, t }: { config: TunnelConfig; result: Record<string, unknown> | null; luminaires: Record<string, unknown> | null; control: Record<string, unknown> | null; tubeIds: string[]; tubeConfigs: Record<string, TunnelConfig>; projectName: string; onChange: (key: string, value: unknown) => void; t: (key: string, params?: Record<string, string | number>) => string }) {
  const [combinedBusy, setCombinedBusy] = useState(false);
  const downloadCombined = async () => {
    setCombinedBusy(true);
    try {
      const tubes = Object.fromEntries(tubeIds.map(id => [id, { form: { ...(tubeConfigs[id] || config), tube_id: id } }]));
      const response = await fetch('/api/tunnel/report-combined', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_name: projectName, report_version: config.report_version || 'v2', tubes }) });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const blob = await response.blob(); const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `informe_tunel_${projectName || 'proyecto'}_combinado.docx`; anchor.click(); URL.revokeObjectURL(url);
    } catch (err) { window.alert(err instanceof Error ? err.message : 'No se pudo generar el informe combinado.'); } finally { setCombinedBusy(false); }
  };
  return <div className="report-workspace-stack"><ReportWorkspaceWithOptions config={config} result={result} luminaires={luminaires} control={control} onChange={onChange} t={t}/><section className="workspace-board report-combined"><div><h3>{t('workspace.downloadCombined')}</h3><p>{t('workspace.combinedHint')}</p></div><button className="secondary" type="button" onClick={() => void downloadCombined()} disabled={combinedBusy || tubeIds.length < 2}>{combinedBusy ? t('workspace.calculating') : t('workspace.downloadCombined')}</button></section></div>;
}

function ReportWorkspaceWithOptions({ config, result, luminaires, control, onChange, t }: { config: TunnelConfig; result: Record<string, unknown> | null; luminaires: Record<string, unknown> | null; control: Record<string, unknown> | null; onChange: (key: string, value: unknown) => void; t: (key: string, params?: Record<string, string | number>) => string }) {
  return <div className="report-workspace-stack"><LegacyReportWorkspace config={config} result={result} luminaires={luminaires} control={control} onChange={onChange} t={t}/></div>;
}

function LegacyReportWorkspace({ config, result, luminaires, control, onChange, t }: { config: TunnelConfig; result: Record<string, unknown> | null; luminaires: Record<string, unknown> | null; control: Record<string, unknown> | null; onChange: (key: string, value: unknown) => void; t: (key: string, params?: Record<string, string | number>) => string }) {
  const [busy, setBusy] = useState('');
  const [reportVersion, setReportVersion] = useState(String(config.report_version || 'v2'));
  useEffect(() => setReportVersion(String(config.report_version || 'v2')), [config.report_version]);
  const ready = result?.success === true && Boolean(luminaires) && Boolean(control);
  const download = async (kind: 'report' | 'excel') => { setBusy(kind); try { const response = await fetch(kind === 'report' ? '/api/tunnel/report' : '/api/tunnel/export-excel', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...config, report_version: reportVersion, stopping_distance_override_m: config.stopping_distance_override_m || config.dp_override, stopping_distance_b_override_m: config.stopping_distance_b_override_m || config.dp_b_override, luminaire: config.lum_config || {}, cie_result: result, control_result: control, luminaires_result: luminaires?.luminaires || null, photometric_result: luminaires?.photometric || null }) }); if (!response.ok) throw new Error(`HTTP ${response.status}`); const blob = await response.blob(); const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = kind === 'report' ? `informe_tunel_${String(config.tube_id || 'T1')}.docx` : `calculo_tunel_${String(config.tube_id || 'T1')}.xlsx`; anchor.click(); URL.revokeObjectURL(url); } catch (err) { window.alert(err instanceof Error ? err.message : 'No se pudo generar el archivo.'); } finally { setBusy(''); } };
  return <div className="workspace-board report-board phase-shell"><div className="board-heading"><div><span className="eyebrow">05 · DELIVERABLES</span><h2>{t('step.report')}</h2><p>{t('workspace.reportHint')}</p></div><span className={`engine-status ${ready ? 'ready' : 'pending'}`}>{ready ? `✓ ${t('workflow.completed')}` : `↻ ${t('workflow.pending')}`}</span></div><div className="phase-guidance"><span className="phase-guidance-number">5</span><div><strong>{t('workspace.reportGuidanceTitle')}</strong><p>{t('workspace.reportGuidance')}</p></div></div><div className="report-checklist"><div className={result?.success ? 'is-ready' : ''}><span>01</span><strong>{t('step.tunnel')}</strong><small>{result?.success ? t('workflow.calculated') : t('workflow.locked')}</small></div><div className={result?.success ? 'is-ready' : ''}><span>02</span><strong>{t('step.zones')}</strong><small>{result?.success ? t('workflow.calculated') : t('workflow.locked')}</small></div><div className={luminaires ? 'is-ready' : ''}><span>03</span><strong>{t('step.luminaires')}</strong><small>{luminaires ? t('workflow.calculated') : t('workflow.locked')}</small></div><div className={control ? 'is-ready' : ''}><span>04</span><strong>{t('step.control')}</strong><small>{control ? t('workflow.calculated') : t('workflow.locked')}</small></div></div><div className="deliverable-grid"><button className="deliverable-card" onClick={() => void download('report')} disabled={busy !== '' || !ready}><span>▤</span><strong>{t('workspace.downloadReport')}</strong><small>DOCX · CIE 88 + CIE 140</small></button><button className="deliverable-card" onClick={() => void download('excel')} disabled={busy !== '' || !ready}><span>▦</span><strong>{t('workspace.downloadExcel')}</strong><small>XLSX · parámetros y resultados</small></button></div><div className="report-note">{t('workspace.reportNote')}</div></div>;
}

function ProjectEditor({ projectId }: { projectId: number }) {
  const { t } = useI18n();
  const [project, setProject] = useState<ProjectRecord | null>(null); const [config, setConfig] = useState<TunnelConfig>(defaultTunnelConfig); const [tubeIds, setTubeIds] = useState<string[]>(['T1']); const [tubeConfigs, setTubeConfigs] = useState<Record<string, TunnelConfig>>({}); const [activeTube, setActiveTube] = useState('T1');
  const [result, setResult] = useState<Record<string, unknown> | null>(null); const [luminaires, setLuminaires] = useState<Record<string, unknown> | null>(null); const [control, setControl] = useState<Record<string, unknown> | null>(null); const [active, setActive] = useState<WorkspaceTab>('tunnel'); const [technicalView, setTechnicalView] = useState<TechnicalView>('plan');
  const [stageStale, setStageStale] = useState<StageStale>({ tunnel: false, luminaire: false, control: false });
  const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [validation, setValidation] = useState<ValidationState | null>(null); const [notice, setNotice] = useState('');

  useEffect(() => { void (async () => { try { const loaded = await getProject(projectId); const saved = loaded.config_json || {}; const savedTubeIds = Array.isArray(saved.tube_ids) ? saved.tube_ids.map(String) : ['T1']; const firstTube = savedTubeIds[0] || 'T1'; const savedTubeConfigs = record(saved.tube_configs) as Record<string, TunnelConfig>; const base = { ...defaultTunnelConfig, ...saved, imd: saved.imd === '' || saved.imd == null ? 500 : saved.imd, project_name: loaded.project_name, tube_id: firstTube }; const firstConfigRaw = { ...base, ...(savedTubeConfigs[firstTube] || {}) }; const firstConfig = { ...firstConfigRaw, imd: firstConfigRaw.imd === '' || firstConfigRaw.imd == null ? 500 : firstConfigRaw.imd }; const savedLuminaires = record(firstConfig.luminaires_result); const savedPhotometric = record(firstConfig.photometric_result); const savedResult = loaded.result_json || null; const savedControl = record(firstConfig.control_result).control ? record(firstConfig.control_result) : null; setProject(loaded); setTubeIds(savedTubeIds.length ? savedTubeIds : ['T1']); setTubeConfigs(savedTubeConfigs); setActiveTube(firstTube); setConfig(firstConfig); setResult(savedResult); setLuminaires(savedLuminaires.zones ? { luminaires: savedLuminaires, photometric: savedPhotometric } : null); setControl(savedControl); setStageStale({ tunnel: false, luminaire: false, control: false }); setActive(savedResult?.success ? 'zones' : 'tunnel'); } catch (err) { setError(err instanceof Error ? err.message : t('editor.projectLoadFailed')); } finally { setLoading(false); } })(); }, [projectId, t]);
  const syncConfig = (next: TunnelConfig) => { setConfig(next); setTubeConfigs(tubes => ({ ...tubes, [activeTube]: next })); };
  const update = (key: string, value: unknown) => { const changesCie = cieInputKeys.has(key); const affectsLuminaire = changesCie || luminaireInputKeys.has(key); const affectsControl = changesCie || controlInputKeys.has(key); if (changesCie) setStageStale(current => ({ tunnel: Boolean(result), luminaire: Boolean(luminaires), control: Boolean(control) })); else if (affectsLuminaire) setStageStale(current => ({ ...current, luminaire: Boolean(luminaires), control: Boolean(control) })); else if (affectsControl) setStageStale(current => ({ ...current, control: Boolean(control) })); setConfig(current => { const next = { ...current, [key]: value }; if (affectsLuminaire) { next.luminaires_result = null; next.photometric_result = null; } if (affectsControl) next.control_result = null; setTubeConfigs(tubes => ({ ...tubes, [activeTube]: next })); return next; }); setValidation(null); if (changesCie) setResult(null); if (affectsLuminaire) setLuminaires(null); if (affectsControl) setControl(null); };
  const updateLum = (key: string, value: unknown) => { if (luminaires || control) setStageStale(current => ({ ...current, luminaire: Boolean(luminaires), control: Boolean(control) })); const next = { ...config, lum_config: { ...record(config.lum_config), [key]: value }, luminaires_result: null, photometric_result: null, control_result: null }; syncConfig(next); setLuminaires(null); setControl(null); };
  const selectTube = (id: string) => { setTubeConfigs(tubes => ({ ...tubes, [activeTube]: config })); const next = { ...defaultTunnelConfig, ...(tubeConfigs[id] || {}), project_name: String(config.project_name || project?.project_name || ''), tube_id: id }; setActiveTube(id); setConfig(next); setResult(null); setLuminaires(record(next.luminaires_result).zones ? record(next.luminaires_result) : null); setControl(record(next.control_result).control ? record(next.control_result) : null); setStageStale({ tunnel: false, luminaire: false, control: false }); setActive('tunnel'); };
  const addTube = () => { const nextId = `T${tubeIds.length + 1}`; const nextConfig = { ...config, tube_id: nextId, project_name: String(config.project_name || project?.project_name || ''), luminaires_result: null, photometric_result: null, control_result: null }; setTubeConfigs(tubes => ({ ...tubes, [activeTube]: config, [nextId]: nextConfig })); setTubeIds(ids => [...ids, nextId]); setActiveTube(nextId); setConfig(nextConfig); setResult(null); setLuminaires(null); setControl(null); setStageStale({ tunnel: false, luminaire: false, control: false }); setActive('tunnel'); };
  const removeTube = (id: string) => { if (tubeIds.length === 1) return; const remaining = tubeIds.filter(tube => tube !== id); const next = remaining[0]; setTubeIds(remaining); setTubeConfigs(tubes => { const copy = { ...tubes }; delete copy[id]; return copy; }); if (id === activeTube) selectTube(next); };
  const save = async (nextResult: Record<string, unknown> | null = result, status = project?.status || 'draft', nextConfig: TunnelConfig = config, artifacts: { luminaires?: unknown; photometric?: unknown; control?: unknown } = {}) => { if (!project) return; const valueFor = (key: 'luminaires' | 'photometric' | 'control', fallback: unknown) => Object.prototype.hasOwnProperty.call(artifacts, key) ? artifacts[key] : fallback; const activeConfig = { ...nextConfig, luminaires_result: valueFor('luminaires', luminaires?.luminaires || nextConfig.luminaires_result || null), photometric_result: valueFor('photometric', luminaires?.photometric || nextConfig.photometric_result || null), control_result: valueFor('control', control || nextConfig.control_result || null) }; const savedConfig = { ...activeConfig, tube_ids: tubeIds, tube_configs: { ...tubeConfigs, [activeTube]: activeConfig } }; const saved = await updateProject(project.id, { project_name: String(activeConfig.project_name || project.project_name), client: project.client || '', location: project.location || '', designer: project.designer || '', study_date: project.study_date || '', reference: project.reference || '', calculation_type: project.calculation_type || 'Iluminación de túneles', standard: project.standard || 'CIE 88:2004 / CIE 140', notes: project.notes || '', status, config_json: savedConfig, result_json: nextResult }); setProject(saved); };
  const validate = async () => { setBusy(true); setError(''); setNotice(''); try { const data = await validateTunnel(config); setValidation(data); if (!data.valid) setError(t('editor.fixBeforeCalculate')); } catch (err) { setError(err instanceof Error ? err.message : t('editor.validationFailed')); } finally { setBusy(false); } };
  const calculate = async () => { setBusy(true); setError(''); setNotice(''); try { const check = await validateTunnel(config); setValidation(check); if (!check.valid) { setActive('tunnel'); setError(t('editor.fixBeforeCalculate')); return; } const data = await calculateTunnel(config); setResult(data); setLuminaires(null); setControl(null); setStageStale({ tunnel: false, luminaire: false, control: false }); await save(data, data.success ? 'calculated' : 'draft', config); setActive(data.success ? 'zones' : 'tunnel'); setNotice(t('editor.calculatedGeometry')); window.setTimeout(() => document.getElementById('tunnel-geometry-definition')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0); } catch (err) { setError(err instanceof Error ? err.message : t('editor.calculationFailed')); } finally { setBusy(false); } };
  const onLuminaires = (data: Record<string, unknown>) => { const next = { ...config, luminaires_result: data.luminaires, photometric_result: data.photometric, control_result: null }; setLuminaires(data); setControl(null); setStageStale(current => ({ ...current, luminaire: false, control: false })); syncConfig(next); void save(result, 'calculated', next, { luminaires: data.luminaires, photometric: data.photometric, control: null }).catch(err => setError(err instanceof Error ? err.message : t('editor.projectSaveFailed'))); setNotice(t('workspace.luminairesCalculated')); };
  const onControl = (data: Record<string, unknown>) => { const next = { ...config, control_result: data }; setControl(data); setStageStale(current => ({ ...current, control: false })); syncConfig(next); void save(result, 'calculated', next, { luminaires: next.luminaires_result, photometric: next.photometric_result, control: data }).catch(err => setError(err instanceof Error ? err.message : t('editor.projectSaveFailed'))); setNotice(t('workspace.controlCalculated')); };
  const goProjects = () => { window.history.pushState({}, '', '/projects'); window.dispatchEvent(new PopStateEvent('popstate')); };
  if (loading) return <div className="app"><Header onProjects={goProjects} /><main className="page loading-card">{t('editor.loading')}</main></div>;
  if (!project) return <div className="app"><Header onProjects={goProjects} /><main className="page"><div className="alert error">{error || t('editor.notFound')}</div></main></div>;
  const hasCie = result?.success === true && !stageStale.tunnel;
  const hasLuminaires = Boolean(luminaires) && !stageStale.luminaire;
  const hasControl = Boolean(control) && !stageStale.control;
  const canOpen = (tab: WorkspaceTab) => tab === 'tunnel' || tab === 'zones' || tab === 'luminaire' ? hasCie || tab === 'tunnel' : tab === 'control' ? hasCie && hasLuminaires : hasCie && hasLuminaires && hasControl;
  const navigate = (tab: WorkspaceTab) => { if (!canOpen(tab)) { setError(t('workflow.lockedMessage')); return; } setError(''); setActive(tab); };
  const statusLabel = (status: string) => t(`workflow.${status}`);
  const tabs: { id: WorkspaceTab; icon: string; label: string; status: string; enabled: boolean }[] = [
    { id: 'tunnel', icon: '▧', label: t('step.tunnel'), status: stageStale.tunnel ? 'stale' : hasCie ? 'calculated' : 'ready', enabled: true },
    { id: 'zones', icon: '◌', label: t('step.zones'), status: hasCie ? 'calculated' : 'locked', enabled: hasCie },
    { id: 'luminaire', icon: '✦', label: t('step.luminaires'), status: stageStale.luminaire ? 'stale' : hasLuminaires ? 'calculated' : hasCie ? 'ready' : 'locked', enabled: hasCie },
    { id: 'control', icon: '⌁', label: t('step.control').replace(/\s+e informes$/i, ''), status: stageStale.control ? 'stale' : hasControl ? 'calculated' : hasLuminaires ? 'ready' : 'locked', enabled: hasCie && hasLuminaires },
    { id: 'report', icon: '▤', label: t('step.report'), status: hasControl ? 'completed' : 'locked', enabled: hasCie && hasLuminaires && hasControl },
  ];
  const calculationStatus = stageStale.tunnel ? { label: 'Cambios pendientes de calcular', tone: 'warning' } : hasCie ? { label: 'Calculado · pendiente de guardar', tone: 'ready' } : { label: 'Pendiente', tone: 'pending' };
  return <div className="app"><Header onProjects={goProjects} /><main className="studio-page">
    <div className="studio-header"><nav className="studio-breadcrumb" aria-label="Navegación del proyecto"><button className="back-link" onClick={goProjects}>{t('editor.back')}</button><span>›</span><strong title={project.project_name}>{project.project_name}</strong><span>›</span><strong>{String(config.tube_id || 'T1')}</strong><small>{project.client || t('editor.noClient')} · {project.location || t('editor.noLocation')}</small></nav><div className="studio-actions"><span className={`calculation-status ${calculationStatus.tone}`}><i />{calculationStatus.label}</span><button className="secondary" onClick={() => void save()}>{t('action.saveDraft')}</button><button className="primary calculate-header-button" onClick={() => void calculate()} disabled={busy}>{busy ? t('action.calculating') : `✓ ${t('workspace.calculateCie')}`}</button></div></div>
    {error && <div className="alert error">{error}</div>}{notice && <div className="alert success">{notice}</div>}
    <div className="tube-switcher"><span>{t('workspace.tubeWorkspace')}</span><div>{tubeIds.map(id => <button type="button" key={id} className={activeTube === id ? 'tube-tab active' : 'tube-tab'} onClick={() => selectTube(id)}>{id}</button>)}<button type="button" className="tube-add" onClick={addTube}>＋ {t('editor.tube')}</button>{tubeIds.length > 1 && <button type="button" className="tube-delete" title={t('editor.deleteTube', { tube: activeTube })} onClick={() => removeTube(activeTube)}>×</button>}</div></div>
    <div className="studio-layout"><nav className="workflow-nav" aria-label={t('aria.configurationSections')}><span className="workflow-label">{t('workspace.workflow')}</span>{tabs.map((tab, index) => <button type="button" key={tab.id} disabled={!tab.enabled} className={`workflow-tab phase-${tab.status}${active === tab.id ? ' active' : ''}${!tab.enabled ? ' is-locked' : ''}`} onClick={() => navigate(tab.id)}><span className="workflow-step-number">{String(index + 1).padStart(2, '0')}</span><span className="workflow-step-copy"><strong><span aria-hidden="true">{tab.icon}</span> {tab.label}</strong><small>{statusLabel(tab.status)}</small></span><i aria-hidden="true">{tab.status === 'locked' ? '·' : tab.status === 'stale' ? '↻' : tab.status === 'completed' ? '✓' : tab.status === 'calculated' ? '✓' : '○'}</i></button>)}<ActiveStepParameters active={active} config={config} result={result} luminaires={luminaires} control={control} technicalView={technicalView} onTechnicalViewChange={setTechnicalView} onChange={update} onLumChange={updateLum} t={t}/><div className="workflow-foot"><span>{t('workspace.standard')}</span><strong>CIE 88 · CIE 140</strong></div></nav>
      <section className="studio-main">{active === 'tunnel' && <TunnelWorkspace config={config} result={result} validation={validation} technicalView={technicalView} onTechnicalViewChange={setTechnicalView} t={t}/>} {active === 'zones' && <ZonesWorkspace config={config} result={result} onOpenLuminaires={() => navigate('luminaire')} t={t}/>} {active === 'luminaire' && <LuminaireWorkspace config={config} result={result} luminaires={luminaires} onCalculated={onLuminaires} onChange={updateLum} onConfigChange={update} busy={busy} setBusy={setBusy} setError={setError} t={t}/>} {active === 'control' && <ControlWorkspace config={config} result={result} luminaires={luminaires} control={control} onCalculated={onControl} onChange={update} onOpenReport={() => navigate('report')} busy={busy} setBusy={setBusy} setError={setError} t={t}/>} {active === 'report' && <ReportWorkspace config={config} result={result} luminaires={luminaires} control={control} tubeIds={tubeIds} tubeConfigs={tubeConfigs} projectName={String(config.project_name || project?.project_name || '')} onChange={update} t={t}/>}</section>
      <LiveEngineeringSummary config={config} result={result} luminaires={luminaires} control={control} active={active} stageStale={stageStale}/>
    </div>
  </main></div>;
}

function ProjectDetails({ project, onChange }: { project: ProjectRecord; onChange: (patch: Partial<ProjectRecord>) => void }) {
  const { t } = useI18n();
  return <Panel title={t('panel.projectTitle')} intro={t('panel.projectIntro')}><div className="form-grid"><TextField label={t('field.projectName')} value={project.project_name} onChange={v => onChange({ project_name: v })} /><TextField label={t('field.client')} value={project.client || ''} onChange={v => onChange({ client: v })} /><TextField label={t('field.location')} value={project.location || ''} onChange={v => onChange({ location: v })} /><TextField label={t('field.designer')} value={project.designer || ''} onChange={v => onChange({ designer: v })} /><TextField label={t('field.studyDate')} type="date" value={project.study_date || ''} onChange={v => onChange({ study_date: v })} /><TextField label={t('field.reference')} value={project.reference || ''} onChange={v => onChange({ reference: v })} /><TextField label={t('field.standard')} value={project.standard || ''} onChange={v => onChange({ standard: v })} /><TextField label={t('field.notes')} value={project.notes || ''} onChange={v => onChange({ notes: v })} textarea /></div></Panel>;
}

function Definition({ config, onChange }: { config: TunnelConfig; onChange: (key: string, value: unknown) => void }) {
  const { t } = useI18n();
  return <div id="tunnel-geometry-definition"><Panel title={t('panel.definitionTitle')} intro={t('panel.definitionIntro')}>
    <SectionTitle title={t('section.mainGeometry')} />
    <div className="form-grid">
      <TextField label={t('field.tubeId')} value={String(config.tube_id || '')} onChange={value => onChange('tube_id', value)} />
      <NumberField label={t('field.length')} unit="m" value={config.length_m} min={10} onChange={value => onChange('length_m', value)} />
      <NumberField label={t('field.speed')} unit="km/h" value={config.speed_kmh} min={20} max={130} step={5} onChange={value => onChange('speed_kmh', value)} />
      <NumberField label={t('field.width')} unit="m" value={config.width_m} min={1} onChange={value => onChange('width_m', value)} />
      <NumberField label={t('field.height')} unit="m" value={config.height_m} min={1} onChange={value => onChange('height_m', value)} />
      <NumberField label={t('field.lanes')} value={config.num_lanes} min={1} step={1} onChange={value => onChange('num_lanes', value)} />
      <NumberField label={t('field.laneWidth')} unit="m" value={config.lane_width_m} min={2.5} onChange={value => onChange('lane_width_m', value)} />
      <SelectField label={t('field.trafficDirection')} value={String(config.traffic_direction)} options={[["one_way", t('option.oneWay')], ["two_way", t('option.twoWay')]]} onChange={value => onChange('traffic_direction', value)} />
      <SelectField label={t('field.tunnelShape')} value={String(config.tunnel_shape)} options={[["horseshoe", t('option.horseshoe')], ["rectangular", t('option.rectangular')], ["circular", t('option.circular')]]} onChange={value => onChange('tunnel_shape', value)} />
    </div>
    <SectionTitle title={t('section.sectionElements')} />
    <div className="form-grid">
      <NumberField label={t('field.gradient')} unit="%" value={config.gradient_pct} onChange={value => onChange('gradient_pct', value)} />
      <NumberField label={t('field.curvature')} unit="m" value={config.curvature_radius_m} onChange={value => onChange('curvature_radius_m', value)} placeholder={t('option.straightPlaceholder')} />
      <NumberField label={t('field.shoulderLeft')} unit="m" value={config.shoulder_left_m} min={0} onChange={value => onChange('shoulder_left_m', value)} />
      <NumberField label={t('field.shoulderRight')} unit="m" value={config.shoulder_right_m} min={0} onChange={value => onChange('shoulder_right_m', value)} />
      <NumberField label={t('field.sidewalkLeft')} unit="m" value={config.sidewalk_left_m} min={0} onChange={value => onChange('sidewalk_left_m', value)} />
      <NumberField label={t('field.sidewalkRight')} unit="m" value={config.sidewalk_right_m} min={0} onChange={value => onChange('sidewalk_right_m', value)} />
      <NumberField label={t('field.wallHeight')} unit="m" value={config.H_pared_m} min={0} onChange={value => onChange('H_pared_m', value)} />
      <SelectField label={t('field.roadSurface')} value={String(config.road_surface)} options={[["dark_asphalt", t('option.darkAsphalt')], ["medium_asphalt", t('option.mediumAsphalt')], ["light_asphalt", t('option.lightAsphalt')], ["concrete", t('option.concrete')], ["bright_concrete", t('option.brightConcrete')]]} onChange={value => onChange('road_surface', value)} />
    </div>
    <div className="design-toggles single-toggle"><Toggle label={t('field.includeShoulders')} checked={Boolean(config.include_shoulders_in_luminance_grid)} onChange={value => onChange('include_shoulders_in_luminance_grid', value)} /></div>
  </Panel></div>;
}

function LegacyDefinition({ config, onChange }: { config: TunnelConfig; onChange: (key: string, value: unknown) => void }) {
  const { t } = useI18n();
  return <div id="tunnel-geometry-definition"><Panel title={t('panel.definitionTitle')} intro={t('panel.definitionIntro')}><SectionTitle title={t('section.mainGeometry')} /><div className="form-grid"><TextField label={t('field.tubeId')} value={String(config.tube_id)} onChange={v => onChange('tube_id', v)} /><NumberField label={t('field.length')} unit="m" value={config.length_m} min={10} onChange={v => onChange('length_m', v)} /><NumberField label={t('field.width')} unit="m" value={config.width_m} min={1} onChange={v => onChange('width_m', v)} /><NumberField label={t('field.height')} unit="m" value={config.height_m} min={1} onChange={v => onChange('height_m', v)} /><NumberField label={t('field.lanes')} value={config.num_lanes} min={1} step={1} onChange={v => onChange('num_lanes', v)} /><NumberField label={t('field.laneWidth')} unit="m" value={config.lane_width_m} min={2.5} onChange={v => onChange('lane_width_m', v)} /><SelectField label={t('field.trafficDirection')} value={String(config.traffic_direction)} options={[["one_way", t('option.oneWay')], ["two_way", t('option.twoWay')]]} onChange={v => onChange('traffic_direction', v)} /><SelectField label={t('field.tunnelShape')} value={String(config.tunnel_shape)} options={[["horseshoe", t('option.horseshoe')], ["rectangular", t('option.rectangular')], ["circular", t('option.circular')]]} onChange={v => onChange('tunnel_shape', v)} /></div><SectionTitle title={t('section.sectionElements')} /><div className="form-grid"><NumberField label={t('field.gradient')} unit="%" value={config.gradient_pct} onChange={v => onChange('gradient_pct', v)} /><NumberField label={t('field.curvature')} unit="m" value={config.curvature_radius_m} onChange={v => onChange('curvature_radius_m', v)} placeholder={t('option.straightPlaceholder')} /><NumberField label={t('field.shoulderLeft')} unit="m" value={config.shoulder_left_m} min={0} onChange={v => onChange('shoulder_left_m', v)} /><NumberField label={t('field.shoulderRight')} unit="m" value={config.shoulder_right_m} min={0} onChange={v => onChange('shoulder_right_m', v)} /><NumberField label={t('field.sidewalkLeft')} unit="m" value={config.sidewalk_left_m} min={0} onChange={v => onChange('sidewalk_left_m', v)} /><NumberField label={t('field.sidewalkRight')} unit="m" value={config.sidewalk_right_m} min={0} onChange={v => onChange('sidewalk_right_m', v)} /><NumberField label={t('field.wallHeight')} unit="m" value={config.H_pared_m} min={0} onChange={v => onChange('H_pared_m', v)} /><SelectField label={t('field.roadSurface')} value={String(config.road_surface)} options={[["dark_asphalt", t('option.darkAsphalt')], ["medium_asphalt", t('option.mediumAsphalt')], ["light_asphalt", t('option.lightAsphalt')], ["concrete", t('option.concrete')], ["bright_concrete", t('option.brightConcrete')]]} onChange={v => onChange('road_surface', v)} /></div></Panel></div>;
}

function StoppingDistanceSummary({ config, t }: { config: TunnelConfig; t: (key: string, params?: Record<string, string | number>) => string }) {
  const speedKmh = Math.max(0, Number(config.speed_kmh) || 80);
  const speedMs = speedKmh / 3.6;
  const gradientPct = Number(config.gradient_pct) || 0;
  const autoMu = automaticFriction(speedKmh);
  const enteredMu = Number(config.mu_friction);
  const mu = Number.isFinite(enteredMu) && enteredMu > 0 ? enteredMu : autoMu;
  const reactionTime = Number(config.t_reaction) || 2.5;
  const effectiveMu = Math.max(0.05, mu - gradientPct / 100);
  const reactionDistance = speedMs * reactionTime;
  const brakingDistance = (speedMs ** 2) / (2 * 9.81 * effectiveMu);
  const automaticDistance = reactionDistance + brakingDistance;
  const enteredDistance = Number(config.dp_override);
  const hasDistanceOverride = Number.isFinite(enteredDistance) && enteredDistance > 0;
  const stoppingDistance = hasDistanceOverride ? enteredDistance : automaticDistance;
  const stoppingTime = reactionTime + speedMs / (9.81 * effectiveMu);
  const format = (value: number) => value.toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const formatMu = (value: number) => value.toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
  const condition = gradientPct > 0
    ? t('stopping.downhill', { value: format(Math.abs(gradientPct)) })
    : gradientPct < 0
      ? t('stopping.uphill', { value: format(Math.abs(gradientPct)) })
      : t('stopping.noGradient');
  const surface = mu >= 0.45 ? t('stopping.drySurface') : t('stopping.wetSurface');

  return <div className="stopping-summary">
    <div className="stopping-summary-heading">
      <strong>🛑 {t('stopping.title')}</strong>
      <span>{t('stopping.badge')}</span>
    </div>
    <div className="stopping-kpis">
      <div className="stopping-kpi">
        <span>{t('result.sd')}</span>
        <strong>{format(stoppingDistance)} m</strong>
        <small>{hasDistanceOverride ? t('stopping.overrideAuto', { value: format(automaticDistance) }) : t('stopping.distanceBreakdown', { reaction: format(reactionDistance), braking: format(brakingDistance) })}</small>
      </div>
      <div className="stopping-kpi">
        <span>{t('stopping.time')}</span>
        <strong>{format(stoppingTime)} s</strong>
        <small>{t('stopping.timeBreakdown', { reaction: format(reactionTime), braking: format(stoppingTime - reactionTime) })}</small>
      </div>
      <div className="stopping-kpi is-green">
        <span>{t('stopping.threshold')}</span>
        <strong>{format(stoppingDistance)} m</strong>
        <small>{t('stopping.thresholdHint')}</small>
      </div>
    </div>
    <p className="stopping-summary-note">{t('stopping.worstCase', { condition, mu: formatMu(mu), surface })}</p>
  </div>;
}

function Parameters({ config, result, onChange }: { config: TunnelConfig; result: Record<string, unknown> | null; onChange: (key: string, value: unknown) => void }) {
  const { t } = useI18n();
  const portalB = oppositeOrientation[String(config.portal_orientation)] || 'N';
  const imd = config.imd === '' || config.imd == null ? 0 : Math.max(0, Number(config.imd) || 0);
  const kPeak = Number(config.k_peak) || 0.10;
  const isTwoWay = String(config.traffic_direction) === 'two_way';
  const trafficFromImd = Math.round(imd * kPeak * (isTwoWay ? 1 : 0.5));
  const speedKmh = Math.max(0, Number(config.speed_kmh) || 80);
  const autoMu = automaticFriction(speedKmh);
  const trafficDesign = Math.max(0, Number(config.traffic_veh_h) || 0);
  const laneCount = Math.max(1, Math.trunc(Number(config.num_lanes) || 1));
  const trafficPerLane = trafficDesign / laneCount;
  const intensityLevel = isTwoWay
    ? (trafficPerLane > 700 ? 'high' : trafficPerLane >= 200 ? 'medium' : 'low')
    : (trafficPerLane > 1500 ? 'high' : trafficPerLane >= 500 ? 'medium' : 'low');
  const calculatedClass = intensityLevel === 'high'
    ? (config.has_pedestrians ? 4 : 3)
    : intensityLevel === 'medium'
      ? (config.has_pedestrians ? 3 : 2)
      : (config.has_pedestrians ? 2 : 1);
  const resultSummary = record(result?.summary);
  const resultLth = record(result?.lth);
  const positiveValue = (value: unknown, fallback = 0) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
  };
  const stoppingDistanceFor = (gradient: number) => {
    const speedMs = speedKmh / 3.6;
    const reaction = Math.max(0, Number(config.t_reaction) || 2.5);
    const friction = Number(config.mu_friction) > 0 ? Number(config.mu_friction) : autoMu;
    const effectiveFriction = Math.max(0.05, friction - gradient / 100);
    return speedMs * reaction + (speedMs ** 2) / (2 * 9.81 * effectiveFriction);
  };
  const dpAutoA = positiveValue(resultLth.SD_calculated_m, stoppingDistanceFor(Number(config.gradient_pct) || 0));
  const dpAutoB = positiveValue(resultLth.SD_b_calculated_m, stoppingDistanceFor(-(Number(config.gradient_pct) || 0)));
  const dpAppliedA = positiveValue(config.dp_override, dpAutoA);
  const dpAppliedB = positiveValue(config.dp_b_override, dpAutoB);
  const l20AutoA = positiveValue(resultLth.L20, positiveValue(resultSummary.L20));
  const l20AutoB = positiveValue(resultLth.L20_b, l20AutoA);
  const classForK = Number.isInteger(Number(config.tunnel_class)) && Number(config.tunnel_class) >= 1 && Number(config.tunnel_class) <= 4
    ? Number(config.tunnel_class)
    : calculatedClass;
  const kFromDistance = (distance: number, tunnelClass: number) => {
    if (tunnelClass === 1) return 0;
    const rows: Record<number, [number, number, number]> = { 2: [0.03, 0.04, 0.05], 3: [0.04, 0.05, 0.07], 4: [0.05, 0.06, 0.10] };
    const [k60, k100, k160] = rows[tunnelClass] || rows[2];
    if (distance <= 60) return k60;
    if (distance <= 100) return k60 + (distance - 60) / 40 * (k100 - k60);
    if (distance < 160) return k100 + (distance - 100) / 60 * (k160 - k100);
    return k160;
  };
  const kAutoA = positiveValue(resultLth.k_factor, kFromDistance(dpAppliedA, classForK));
  const kAutoB = positiveValue(resultLth.k_factor_b, kFromDistance(dpAppliedB, classForK));
  const lseqAutoA = positiveValue(resultSummary.Lseq);
  const lseqAutoB = positiveValue(resultLth.Lseq_b, lseqAutoA);
  const lthAutoA = positiveValue(resultLth.Lth_auto, positiveValue(resultSummary.Lth));
  const lthAutoB = positiveValue(resultLth.Lth_b_auto, lthAutoA);
  const formatAutomatic = (value: number, digits = 1) => value > 0 ? value.toFixed(digits) : '';
  const applyImd = () => { if (imd > 0) onChange('traffic_veh_h', trafficFromImd); };
  return <Panel title={t('panel.parametersTitle')} intro={t('panel.parametersIntro')}>
    <SectionTitle title={t('section.environment')} />
    <div className="form-grid">
      <SelectField label={t('field.environmentType')} value={String(config.environment_type || 'open_country_flat')} options={[["open_country_flat", t('option.environmentOpenFlat')], ["open_country_hilly", t('option.environmentOpenHilly')], ["forest", t('option.environmentForest')], ["urban", t('option.environmentUrban')], ["mountain", t('option.environmentMountain')], ["coastal", t('option.environmentCoastal')], ["desert", t('option.environmentDesert')]]} onChange={v => onChange('environment_type', v)} />
      <SelectField label={t('field.designSky')} value={String(config.sky_condition)} options={[["clear", t('option.clear')], ["intermediate", t('option.intermediate')], ["overcast", t('option.overcast')]]} onChange={v => onChange('sky_condition', v)} />
      <SelectField label={t('field.daylight')} value={String(config.daylight_penetration)} options={[["poor", t('option.poor')], ["good", t('option.good')]]} onChange={v => onChange('daylight_penetration', v)} />
      <NumberField label={t('field.wallReflectance')} unit="ρ" value={config.wall_reflectance} min={0.05} max={0.95} step={0.05} onChange={v => onChange('wall_reflectance', v)} />
      <NumberField label={t('field.wallLuminanceHeight')} unit="m" value={config.wall_luminance_height_m} min={0.5} max={5.5} step={0.1} onChange={v => onChange('wall_luminance_height_m', v)} />
      <NumberField label={t('field.wallRatio')} value={config.wall_ratio_override} min={0.05} max={2} step={0.01} placeholder={t('option.autoPlaceholder')} onChange={v => onChange('wall_ratio_override', v)} />
      <SelectField label={t('field.l20Method')} value={String(config.l20_method)} options={[["model", t('option.model')], ["table", t('option.table')]]} onChange={v => onChange('l20_method', v)} />
      <NumberField label={t('field.ambientTemp')} unit="°C" value={config.ta_design_c} onChange={v => onChange('ta_design_c', v)} />
    </div>
    <div className="environment-toggles">
      <Toggle label={t('field.exitVisible')} checked={Boolean(config.exit_visible)} onChange={v => onChange('exit_visible', v)} />
      <Toggle label={t('field.roadLit')} checked={Boolean(config.illuminated_road)} onChange={v => onChange('illuminated_road', v)} />
    </div>

    <div className="imd-card imd-parameter-card">
      <div className="imd-card-heading"><strong>{t('imd.title')}</strong><a href="https://mapadetrafico.transportes.gob.es/" target="_blank" rel="noopener noreferrer">{t('imd.dgt')}</a></div>
      <div className="form-grid">
        <NumberField label={t('field.aadt')} value={config.imd} min={0} max={200000} step={500} placeholder="15000" onChange={v => onChange('imd', v)} />
        <SelectField label={t('imd.kPeak')} value={kPeak.toFixed(2)} options={[["0.08", t('imd.kRural')], ["0.10", t('imd.kStandard')], ["0.11", t('imd.kMainRoad')], ["0.12", t('imd.kUrban')], ["0.14", t('imd.kCongested')]]} onChange={v => onChange('k_peak', Number(v))} />
      </div>
      <div className={`imd-calculation${imd > 0 ? ' active' : ''}`}>
        <span className="imd-formula">{imd > 0 ? imd.toLocaleString('es-ES') : 'IMD'} × {kPeak.toFixed(2)}{isTwoWay ? '' : ' ÷ 2'} =</span>
        <span className="imd-result"><strong>{imd > 0 ? trafficFromImd.toLocaleString('es-ES') : '—'} veh/h</strong><small>({isTwoWay ? t('imd.twoWayTube') : t('imd.oneWayTube')})</small></span>
        <button type="button" className="imd-apply" onClick={applyImd} disabled={imd <= 0}>{t('imd.apply')}</button>
      </div>
      <p className="imd-note">{t('imd.note')}</p>
    </div>
    <SectionTitle title={t('section.design')} />
    <div className="form-grid">
      <NumberField label={t('field.designTraffic')} unit="veh/h" value={config.traffic_veh_h} min={0} onChange={v => onChange('traffic_veh_h', v)} />
      <NumberField label={t('field.interiorLuminance')} unit="cd/m²" value={config.interior_luminance_override} min={0} max={100} step={0.1} placeholder={t('option.autoPlaceholder')} onChange={v => onChange('interior_luminance_override', v)} />
      <SelectField label={t('field.lthStandard')} value={String(config.lth_standard || 'oc36_2015')} options={[["oc36_2015", t('option.oc362015')], ["cie88", t('option.cie88')]]} onChange={v => onChange('lth_standard', v)} />
      <SelectField label={t('field.lthMethod')} value={String(config.lth_method)} options={[["k_factor", t('option.recommended')], ["lseq", t('option.lseqAdvanced')]]} onChange={v => onChange('lth_method', v)} />
      <SelectField label={t('field.tunnelClass')} value={String(config.tunnel_class)} options={[["auto", t('option.autoClass', { class: calculatedClass })], ["1", t('option.class1')], ["2", t('option.class2')], ["3", t('option.class3')], ["4", t('option.class4')]]} onChange={v => onChange('tunnel_class', v)} />
    </div>
    <div className="design-toggles">
      <Toggle label={t('field.pedestrians')} checked={Boolean(config.has_pedestrians)} onChange={v => onChange('has_pedestrians', v)} />
      <Toggle label={t('field.stepped')} checked={Boolean(config.profile_stepped)} onChange={v => onChange('profile_stepped', v)} />
    </div>
    {Boolean(config.profile_stepped) && <div className="stepped-settings">
      <NumberField label={t('field.steps')} value={config.n_steps} min={2} max={8} step={1} onChange={v => onChange('n_steps', v)} />
    </div>}

    <SectionTitle title={t('section.stoppingDistance')} />
    <div className="form-grid stopping-distance-fields">
      <NumberField label={t('field.reaction')} unit="s" value={config.t_reaction} min={1} max={4} step={0.5} onChange={v => onChange('t_reaction', v)} />
      <NumberField label={t('field.friction')} hint={t('stopping.autoValue', { value: autoMu.toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 2 }), speed: speedKmh })} value={Number(config.mu_friction) > 0 ? config.mu_friction : autoMu} min={0.15} max={0.65} step={0.01} onChange={v => onChange('mu_friction', v)} />
    </div>
    <StoppingDistanceSummary config={config} t={t} />

    <div className="lth-input-card">
      <div className="lth-card-heading"><strong>🔆 {t('lth.cardTitle')}</strong><span>{t('lth.cardBadge')}</span></div>
      <div className="lth-core-grid">
        <NumberField label={t('lth.l20', { portal: String(config.portal_orientation) })} value={config.l20_override} min={1} max={30000} step={10} placeholder={l20AutoA > 0 ? `Auto: ${formatAutomatic(l20AutoA, 0)}` : t('lth.autoModel')} onChange={v => onChange('l20_override', v)} />
        {isTwoWay && <NumberField label={t('lth.l20', { portal: portalB })} value={config.l20_b_override} min={1} max={30000} step={10} placeholder={l20AutoB > 0 ? `Auto: ${formatAutomatic(l20AutoB, 0)}` : t('lth.autoOrientation')} onChange={v => onChange('l20_b_override', v)} />}
        <NumberField label={t('lth.dp', { portal: String(config.portal_orientation) })} value={config.dp_override} min={10} max={500} step={1} placeholder={dpAutoA > 0 ? t('lth.autoValue', { value: formatAutomatic(dpAutoA) }) : t('option.calculated')} onChange={v => onChange('dp_override', v)} />
        {isTwoWay && <NumberField label={t('lth.dp', { portal: portalB })} value={config.dp_b_override} min={10} max={500} step={1} placeholder={dpAutoB > 0 ? t('lth.autoValue', { value: formatAutomatic(dpAutoB) }) : t('option.calculated')} onChange={v => onChange('dp_b_override', v)} />}
        {String(config.lth_method) === 'k_factor' ? <>
          <NumberField label={t('lth.k', { portal: String(config.portal_orientation) })} value={config.k_lth_override} min={0} max={0.25} step={0.001} placeholder={kAutoA > 0 ? t('lth.autoValue', { value: kAutoA.toFixed(4) }) : t('option.autoPlaceholder')} onChange={v => onChange('k_lth_override', v)} />
          {isTwoWay && <NumberField label={t('lth.k', { portal: portalB })} value={config.k_lth_b_override} min={0} max={0.25} step={0.001} placeholder={kAutoB > 0 ? t('lth.autoValue', { value: kAutoB.toFixed(4) }) : t('option.autoPlaceholder')} onChange={v => onChange('k_lth_b_override', v)} />}
        </> : <>
          <NumberField label={t('lth.lseq', { portal: String(config.portal_orientation) })} value={config.lseq_override} min={0} max={30000} step={10} placeholder={lseqAutoA > 0 ? t('lth.autoValue', { value: lseqAutoA.toFixed(0) }) : t('lth.autoLseq')} onChange={v => onChange('lseq_override', v)} />
          {isTwoWay && <NumberField label={t('lth.lseq', { portal: portalB })} value={config.lseq_b_override} min={0} max={30000} step={10} placeholder={lseqAutoB > 0 ? t('lth.autoValue', { value: lseqAutoB.toFixed(0) }) : t('lth.autoLseq')} onChange={v => onChange('lseq_b_override', v)} />}
          <NumberField label={t('lth.qc')} value={config.qc_override ?? 0.1} min={0.01} max={1.5} step={0.01} onChange={v => onChange('qc_override', v)} />
          <NumberField label={t('lth.contrast')} value={config.contrast_observation ?? 0.04} min={0.01} max={0.99} step={0.01} onChange={v => onChange('contrast_observation', v)} />
        </>}
      </div>
      <div className="lth-direct-grid">
        <NumberField label={t('lth.direct', { portal: String(config.portal_orientation) })} unit="cd/m²" value={config.lth_override} min={0} placeholder={t('option.autoPlaceholder')} onChange={v => onChange('lth_override', v)} />
        {isTwoWay && <NumberField label={t('lth.direct', { portal: portalB })} unit="cd/m²" value={config.lth_b_override} min={0} placeholder={t('option.autoPlaceholder')} onChange={v => onChange('lth_b_override', v)} />}
      </div>
      <div className={`lth-chain-note ${String(config.lth_method) === 'k_factor' ? 'is-k-factor' : 'is-lseq'}`}>
        {String(config.lth_method) === 'k_factor' ? <>
          <strong>{t('lth.chainLabel')}</strong>{' '}{t('lth.chainK', { class: classForK, distance: formatAutomatic(dpAppliedA), k: kAutoA.toFixed(4) })}{lthAutoA > 0 && <b>{` ≈ ${Math.ceil(lthAutoA - 1e-9)} cd/m²`}</b>}
          <small>{t('lth.qcUnused')}</small>
        </> : <>
          <strong>{t('lth.chainLabel')}</strong>{' '}{t('lth.chainLseq')}{lthAutoA > 0 && <b>{` ≈ ${Math.ceil(lthAutoA - 1e-9)} cd/m²`}</b>}
          <small>{t('lth.qcAdvanced')}</small>
        </>}
        <div className="lth-chain-foot">{t('lth.emptyOverride')}</div>
      </div>
    </div>
    <div className="project-geometry-card">
      <div className="project-geometry-heading"><strong>⚠ {t('lth.geometryTitle')}</strong></div>
      <p>{t('lth.geometryHint')}</p>
      <div className="project-geometry-grid">
        <NumberField label={t('lth.threshold', { portal: String(config.portal_orientation) })} hint={t('lth.emptyDp', { value: formatAutomatic(dpAppliedA) })} value={config.threshold_length_override_m} min={1} max={1000} step={1} placeholder={t('lth.sameAsDp')} onChange={v => onChange('threshold_length_override_m', v)} />
        {isTwoWay && <NumberField label={t('lth.threshold', { portal: portalB })} hint={t('lth.emptyDp', { value: formatAutomatic(dpAppliedB) })} value={config.threshold_length_b_override_m} min={1} max={1000} step={1} placeholder={t('lth.sameAsDp')} onChange={v => onChange('threshold_length_b_override_m', v)} />}
        <NumberField label={t('lth.transitionEnd', { portal: String(config.portal_orientation) })} hint={t('lth.transitionHint')} value={config.transition_end_override_m} min={1} max={3000} step={1} placeholder={t('lth.cieCalculated')} onChange={v => onChange('transition_end_override_m', v)} />
        {isTwoWay && <NumberField label={t('lth.transitionEnd', { portal: portalB })} hint={t('lth.transitionHint')} value={config.transition_end_b_override_m} min={1} max={3000} step={1} placeholder={t('lth.cieCalculated')} onChange={v => onChange('transition_end_b_override_m', v)} />}
        {!isTwoWay && <>
          <NumberField label={t('lth.exitLength')} hint={t('lth.emptyDp', { value: formatAutomatic(dpAppliedA) })} value={config.exit_length_override_m} min={1} max={1000} step={1} placeholder={t('lth.sameAsDp')} onChange={v => onChange('exit_length_override_m', v)} />
          <NumberField label={t('lth.exitRatio')} hint={t('lth.exitRatioHint')} value={config.exit_luminance_ratio_override ?? 100} min={0} max={200} step={1} placeholder="100" onChange={v => onChange('exit_luminance_ratio_override', v)} />
        </>}
      </div>
    </div>

   </Panel>;
}

function ValidationPanel({ validation, onValidate, busy }: { validation: { valid: boolean; errors: string[]; warnings: string[] } | null; onValidate: () => void; busy: boolean }) {
  const { t } = useI18n();
  return <Panel title={t('panel.validationTitle')} intro={t('panel.validationIntro')}><button className="primary" onClick={onValidate} disabled={busy}>{busy ? t('action.validating') : t('action.validate')}</button>{validation && <div className="validation-list"><div className={`validation-banner ${validation.valid ? 'valid' : 'invalid'}`}>{validation.valid ? t('validation.ready') : t('validation.attention')}</div>{validation.errors.map(item => <div className="validation-item error" key={item}>✕ {item}</div>)}{validation.warnings.map(item => <div className="validation-item warning" key={item}>⚠ {item}</div>)}</div>}</Panel>;
}

function Results({ result }: { result: Record<string, unknown> | null }) {
  const { t } = useI18n();
  const summary = (result?.summary || {}) as Record<string, unknown>; const zones = (result?.zones || {}) as Record<string, Record<string, unknown>>;
  if (!result) return <Panel title={t('panel.resultsTitle')} intro={t('panel.resultsIntro')}><div className="empty-results">{t('panel.resultsEmpty')}</div></Panel>;
  return <Panel title={t('panel.resultsTitle')} intro={t('panel.resultsIntro')}><div className="kpi-grid"><Kpi label={t('result.lth')} value={formatNumber(summary.Lth)} unit="cd/m²" /><Kpi label={t('result.lin')} value={formatNumber(summary.Lin)} unit="cd/m²" /><Kpi label={t('result.sd')} value={formatNumber(summary.SD_m, 0)} unit="m" /><Kpi label={t('result.status')} value={result.success ? t('result.calculated') : t('result.review')} /></div><SectionTitle title={t('section.normativeZones')} /><div className="table-wrap"><table><thead><tr><th>{t('result.zone')}</th><th>{t('result.start')}</th><th>{t('result.end')}</th><th>{t('result.required')}</th><th>{t('result.status')}</th></tr></thead><tbody>{Object.entries(zones).map(([key, zone]) => <tr key={key}><td><strong>{String(zone.zone_name || t(`zone.${key}`))}</strong></td><td>{formatNumber(zone.s_start, 1)} m</td><td>{formatNumber(zone.s_end, 1)} m</td><td>{formatNumber(zone.L_min_required || zone.L_required)} cd/m²</td><td>{zone.compliant === false ? <span className="fail">{t('result.notCompliant')}</span> : <span className="pass">{t('result.compliant')}</span>}</td></tr>)}</tbody></table></div><pre className="result-note">{result.warnings ? t('result.warnings', { count: (result.warnings as string[]).length }) : ''}{t('result.note')}</pre></Panel>;
}

function ControlPanel({ project, config, onSave }: { project: ProjectRecord; config: TunnelConfig; onSave: () => void }) {
  const { t } = useI18n();
  return <Panel title={t('panel.controlTitle')} intro={t('panel.controlIntro')}><div className="info-box"><strong>{project.project_name}</strong><p>{t('panel.controlReady')}</p></div><button className="secondary" onClick={onSave}>{t('action.saveConfig')}</button></Panel>;
}

function Panel({ title, intro, children }: { title: string; intro: string; children: ReactNode }) { return <div className="panel"><div className="panel-heading"><h2>{title}</h2><p>{intro}</p></div>{children}</div>; }
function SectionTitle({ title }: { title: string }) { return <h3 className="section-title">{title}</h3>; }
function Kpi({ label, value, unit }: { label: string; value: string; unit?: string }) { return <div className="kpi"><small>{label}</small><strong>{value || '—'}{unit && <em> {unit}</em>}</strong></div>; }
function TextField({ label, value, onChange, placeholder, type = 'text', required = false, textarea = false }: { label: string; value: string; onChange: (value: string) => void; placeholder?: string; type?: string; required?: boolean; textarea?: boolean }) { return <label className={textarea ? 'field wide' : 'field'}><span>{label}</span>{textarea ? <textarea value={value} onChange={event => onChange(event.target.value)} placeholder={placeholder} rows={3} required={required} /> : <input type={type} value={value} onChange={event => onChange(event.target.value)} placeholder={placeholder} required={required} />}</label>; }
function NumberField({ label, value, onChange, unit, min, max, step = 0.1, placeholder, hint }: { label: string; value: unknown; onChange: (value: number | string) => void; unit?: string; min?: number; max?: number; step?: number; placeholder?: string; hint?: string }) { return <label className="field"><span>{label}</span>{hint && <small className="field-hint">{hint}</small>}<div className="input-unit"><input type="number" value={value == null ? '' : String(value)} onChange={event => onChange(event.target.value === '' ? '' : Number(event.target.value))} min={min} max={max} step={step} placeholder={placeholder} />{unit && <em>{unit}</em>}</div></label>; }
function SelectField({ label, value, options, onChange }: { label: string; value: string; options: string[][]; onChange: (value: string) => void }) { return <label className="field"><span>{label}</span><select value={value} onChange={event => onChange(event.target.value)}>{options.map(([option, text]) => <option key={option} value={option}>{text}</option>)}</select></label>; }
function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) { return <label className={`toggle-field${checked ? ' is-checked' : ''}`}><input type="checkbox" checked={checked} onChange={event => onChange(event.target.checked)} /><span className="toggle-control" aria-hidden="true"><span className="toggle-thumb" /></span><span className="toggle-label">{label}</span></label>; }
function ModalShell({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) { const { t } = useI18n(); return <div className="modal-backdrop"><div className="modal"><div className="modal-header"><div><h2>{title}</h2><p>{t('modal.hint')}</p></div><button className="close" onClick={onClose} aria-label={t('aria.close')}>×</button></div><div className="modal-body">{children}</div></div></div>; }
function formatDate(value?: string | null, language: string = 'ES') { if (!value) return '—'; const date = new Date(value); const locale: Record<string, string> = { ES: 'es-ES', EN: 'en-GB', FR: 'fr-FR', CA: 'ca-ES', IT: 'it-IT' }; return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(locale[language] || 'en-GB'); }
function formatNumber(value: unknown, digits = 1) { const number = Number(value); return Number.isFinite(number) ? number.toFixed(digits) : '—'; }

export default App;
