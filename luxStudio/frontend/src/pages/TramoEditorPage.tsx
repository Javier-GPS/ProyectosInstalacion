import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { Calculator } from 'lucide-react';
import { useI18n } from '../i18n';
import { useConfigStore, type ConfigState, type SavedSnapshot } from '../store/useConfigStore';
import { useShallow } from 'zustand/react/shallow';
import { useUnsavedChangesGuard } from '../hooks/useUnsavedChangesGuard';
import { getProject, type ProjectRecord } from '../lib/projects';
import {
  getTramo,
  createTramo,
  updateTramo,
} from '../lib/tramos';
import {
  autoOptimizationConfigHash,
  buildCalculationRequest,
  calculationConfigHash,
  configHash,
  withHash,
} from '../lib/tramoRequest';
import type {
  AdvancedOptimizationLimits,
  AdvancedOptimizationObjective,
  AdvancedOptimizationVariables,
  BatchCalculationResponse,
  OptimizationLensResult,
  OptimizationResponse,
  CalculationResult as TSCalculationResult,
  TramoRecord,
} from '../types';

import ConfigurationTabsPanel from '../components/panels/ConfigurationTabsPanel';
import AutoOptimizePanel from '../components/panels/AutoOptimizePanel';
import BatchResultsPanel from '../components/panels/BatchResultsPanel';
import QuickInfoPanel from '../components/panels/QuickInfoPanel';
import RoadViewContainer from '../components/canvas/RoadViewContainer';
import { TramoNameInput, UnsavedChangesModal, SaveOptionsModal, RecalcPromptModal, AdvancedOptimizationResultsModal, CalculatorModal } from '../components/tramos';

const formatWatts = (value: number) => `${value.toFixed(1)} W`;
const formatMeters = (value: number) => `${value.toFixed(1)} m`;
const formatDegrees = (value: number) => `${value.toFixed(0)} deg`;

const REQUEST_FIELDS = [
  'road_width', 'sidewalk_left', 'sidewalk_right', 'lanes', 'median_width',
  'arrangement', 'height', 'spacing', 'arm_length', 'pole_offset', 'pole_side', 'tilt',
  'optic_family', 'target_flux', 'power', 'ldt_id', 'manufacturer', 'model_family',
  'gama', 'difusor', 'lente', 'led_type',
  'lighting_class', 'sidewalk_left_class', 'sidewalk_right_class', 'median_class',
  'mf', 'pavement', 'cct', 'cri', 't_amb_c', 'margen_lavg', 'i_op_ma', 'lm_w_min', 'language', 'driverEfficiency',
  'illuminance_scale_mode', 'illuminance_scale_min', 'illuminance_scale_max',
  'photometric_display_unit', 'generate_buildings', 'building_height', 'buildings_as_obstacles',
] as const satisfies ReadonlyArray<keyof ConfigState>;

type RequestSnapshot = Pick<ConfigState, (typeof REQUEST_FIELDS)[number]>;

const requestSnapshotSelector = (s: ConfigState): RequestSnapshot => {
  const out = {} as RequestSnapshot;
  for (const k of REQUEST_FIELDS) {
    (out as any)[k] = s[k];
  }
  return out;
};

const buildOptimizationChanges = (
  beforeConfig: ReturnType<typeof buildCalculationRequest>,
  afterConfig: any,
) => {
  const beforePower = Number(beforeConfig.power);
  const afterPower = Number(afterConfig.power ?? beforePower);
  const beforeSpacing = Number(beforeConfig.spacing);
  const afterSpacing = Number(afterConfig.spacing ?? beforeSpacing);
  const beforeHeight = Number(beforeConfig.height);
  const afterHeight = Number(afterConfig.height ?? beforeHeight);
  const beforeArmLength = Number(beforeConfig.arm_length);
  const afterArmLength = Number(afterConfig.arm_length ?? afterConfig.armLength ?? beforeArmLength);
  const beforeTilt = Number(beforeConfig.tilt);
  const afterTilt = Number(afterConfig.tilt ?? afterConfig.armTiltAngle ?? beforeTilt);
  const changes = [];

  if (Number.isFinite(beforePower) && Number.isFinite(afterPower) && Math.abs(beforePower - afterPower) >= 0.05) {
    changes.push({ label: 'power', before: formatWatts(beforePower), after: formatWatts(afterPower) });
  }
  if (Number.isFinite(beforeSpacing) && Number.isFinite(afterSpacing) && Math.abs(beforeSpacing - afterSpacing) >= 0.05) {
    changes.push({ label: 'spacing', before: formatMeters(beforeSpacing), after: formatMeters(afterSpacing) });
  }
  if (Number.isFinite(beforeHeight) && Number.isFinite(afterHeight) && Math.abs(beforeHeight - afterHeight) >= 0.05) {
    changes.push({ label: 'height', before: formatMeters(beforeHeight), after: formatMeters(afterHeight) });
  }
  if (Number.isFinite(beforeArmLength) && Number.isFinite(afterArmLength) && Math.abs(beforeArmLength - afterArmLength) >= 0.05) {
    changes.push({ label: 'arm_length', before: formatMeters(beforeArmLength), after: formatMeters(afterArmLength) });
  }
  if (Number.isFinite(beforeTilt) && Number.isFinite(afterTilt) && Math.abs(beforeTilt - afterTilt) >= 0.5) {
    changes.push({ label: 'tilt', before: formatDegrees(beforeTilt), after: formatDegrees(afterTilt) });
  }
  return changes;
};

const buildOptimizationReport = (
  beforeConfig: ReturnType<typeof buildCalculationRequest>,
  data: OptimizationResponse,
) => ({
  feasible: data.feasible,
  message: data.message,
  objective: data.objective,
  checked: data.checked,
  changes: buildOptimizationChanges(beforeConfig, data.config ?? data.result?.config ?? beforeConfig),
});

const roadElementsFromFlat = (config: Record<string, any>): import('../types').RoadElement[] => {
  const elements: import('../types').RoadElement[] = [];
  const sl = typeof config.sidewalk_left === 'number' ? config.sidewalk_left : 0;
  const sr = typeof config.sidewalk_right === 'number' ? config.sidewalk_right : 0;
  const rw = typeof config.road_width === 'number' ? config.road_width : 7;
  const ln = typeof config.lanes === 'number' ? config.lanes : 2;
  const lc = config.lighting_class || 'M3';
  const mw = typeof config.median_width === 'number' ? config.median_width : 0;
  const slc = config.sidewalk_left_class || 'P4';
  const src = config.sidewalk_right_class || 'P4';
  const mc = config.median_class || 'P4';
  if (sl > 0) elements.push({ type: 'sidewalk', width: sl, pedestrian_class: slc });
  elements.push({ type: 'carriageway', width: rw, lanes: ln, lighting_class: lc });
  if (mw > 0) elements.push({ type: 'sidewalk', width: mw, pedestrian_class: mc });
  if (sr > 0) elements.push({ type: 'sidewalk', width: sr, pedestrian_class: src });
  return elements;
};

const applyTramoConfig = (
  tramo: TramoRecord,
  setters: {
    setRoadElements: (el: import('../types').RoadElement[]) => void;
    setRoadWidth: (w: number) => void;
    setSidewalkLeft: (w: number) => void;
    setSidewalkRight: (w: number) => void;
    setLanes: (n: number) => void;
    setMedianWidth: (w: number) => void;
    setArrangement: (a: any) => void;
    setHeight: (h: number) => void;
    setSpacing: (s: number) => void;
    setArmLength: (a: number) => void;
    setPoleOffset: (o: number) => void;
    setPoleSide: (s: any) => void;
    setTilt: (t: number) => void;
    setOpticFamily: (f: string) => void;
    setTargetFlux: (f: number) => void;
    setPower: (p: number) => void;
    setManufacturer: (m: string) => void;
    setModelFamily: (m: string) => void;
    setGama: (g: string) => void;
    setDifusor: (d: string) => void;
    setLente: (l: string) => void;
    setLedType: (lt: string) => void;
    setSelectedLdt: (ldt: { id: string; manufacturer: string; model_family: string; optic_family: string }) => void;
    setLightingClass: (c: any) => void;
    setSidewalkLeftClass: (c: string) => void;
    setSidewalkRightClass: (c: string) => void;
    setMedianClass: (c: string) => void;
    setMf: (m: number) => void;
    setPavement: (p: any) => void;
    setCct: (c: number) => void;
    setCri: (c: any) => void;
    setTAmbC: (t: number) => void;
    setMargenLavg: (m: number) => void;
    setIOpMa: (m: number | null) => void;
    setLmWMin: (m: number | null) => void;
    setDriverEfficiency: (value: number) => void;
    setIlluminanceScaleMode: (mode: any) => void;
    setIlluminanceScaleMin: (value: number) => void;
    setIlluminanceScaleMax: (value: number) => void;
    setPhotometricDisplayUnit: (unit: any) => void;
    setGenerateBuildings: (enabled: boolean) => void;
    setBuildingHeight: (height: number) => void;
    setBuildingsAsObstacles: (enabled: boolean) => void;
    setResults: (r: any) => void;
  },
) => {
  if (!tramo.config_json) return;
  try {
    const config = JSON.parse(tramo.config_json);
    const re: import('../types').RoadElement[] = Array.isArray(config.road_elements) && config.road_elements.length > 0
      ? config.road_elements.map((el: any) => ({
          ...el,
          lighting_class: el.lighting_class || null,
          pedestrian_class: el.pedestrian_class || null,
          lanes: el.lanes ?? null,
        }))
      : roadElementsFromFlat(config);
    setters.setRoadElements(re);
    if (typeof config.road_width === 'number') setters.setRoadWidth(config.road_width);
    if (typeof config.sidewalk_left === 'number') setters.setSidewalkLeft(config.sidewalk_left);
    if (typeof config.sidewalk_right === 'number') setters.setSidewalkRight(config.sidewalk_right);
    if (typeof config.lanes === 'number') setters.setLanes(config.lanes);
    if (typeof config.median_width === 'number') setters.setMedianWidth(config.median_width);
    if (config.arrangement) setters.setArrangement(config.arrangement);
    if (typeof config.height === 'number') setters.setHeight(config.height);
    if (typeof config.spacing === 'number') setters.setSpacing(config.spacing);
    if (typeof config.arm_length === 'number') setters.setArmLength(config.arm_length);
    if (typeof config.pole_offset === 'number') setters.setPoleOffset(config.pole_offset);
    if (config.pole_side) setters.setPoleSide(config.pole_side);
    if (typeof config.tilt === 'number') setters.setTilt(config.tilt);
    if (config.optic_family) setters.setOpticFamily(config.optic_family);
    if (typeof config.target_flux === 'number') setters.setTargetFlux(config.target_flux);
    if (typeof config.power === 'number') setters.setPower(config.power);
    if (config.manufacturer) setters.setManufacturer(config.manufacturer);
    if (config.model_family) setters.setModelFamily(config.model_family);
    setters.setGama(config.gama || '');
    setters.setDifusor(config.difusor || '');
    setters.setLente(config.lente || '');
    setters.setLedType(config.led_type || '');
    if (config.ldt_id || config.manufacturer || config.model_family || config.optic_family) {
      setters.setSelectedLdt({
        id: config.ldt_id || '',
        manufacturer: config.manufacturer || '',
        model_family: config.model_family || '',
        optic_family: config.optic_family || '',
      });
    }
    if (config.lighting_class) setters.setLightingClass(config.lighting_class);
    if (config.sidewalk_left_class) setters.setSidewalkLeftClass(config.sidewalk_left_class);
    if (config.sidewalk_right_class) setters.setSidewalkRightClass(config.sidewalk_right_class);
    if (config.median_class) setters.setMedianClass(config.median_class);
    if (typeof config.mf === 'number') setters.setMf(config.mf);
    if (config.pavement) setters.setPavement(config.pavement);
    if (typeof config.cct === 'number') setters.setCct(config.cct);
    if (typeof config.cri === 'number') setters.setCri(config.cri);
    if (typeof config.t_amb_c === 'number') setters.setTAmbC(config.t_amb_c);
    if (typeof config.margen_lavg === 'number') setters.setMargenLavg(config.margen_lavg);
    setters.setIOpMa(typeof config.i_op_ma === 'number' ? config.i_op_ma : null);
    setters.setLmWMin(typeof config.lm_w_min === 'number' ? config.lm_w_min : null);
    const driverEfficiency = config.driverEfficiency ?? config.driver_eficiencia;
    if (typeof driverEfficiency === 'number') setters.setDriverEfficiency(driverEfficiency);
    if (config.illuminance_scale_mode) setters.setIlluminanceScaleMode(config.illuminance_scale_mode);
    if (typeof config.illuminance_scale_min === 'number') setters.setIlluminanceScaleMin(config.illuminance_scale_min);
    if (typeof config.illuminance_scale_max === 'number') setters.setIlluminanceScaleMax(config.illuminance_scale_max);
    if (config.photometric_display_unit) setters.setPhotometricDisplayUnit(config.photometric_display_unit);
    if (typeof config.generate_buildings === 'boolean') setters.setGenerateBuildings(config.generate_buildings);
    if (typeof config.building_height === 'number') setters.setBuildingHeight(config.building_height);
    if (typeof config.buildings_as_obstacles === 'boolean') setters.setBuildingsAsObstacles(config.buildings_as_obstacles);
    if (tramo.result_json) {
      setters.setResults(JSON.parse(tramo.result_json));
    } else {
      setters.setResults(null);
    }
  } catch (err) {
    console.error(err);
  }
};

const snapshotConfig = (): SavedSnapshot => {
  const config = useConfigStore.getState();
  const request = buildCalculationRequest();
  return {
    configJson: withHash(request, configHash(request)),
    resultJson: config.results ? JSON.stringify(config.results) : null,
  };
};

const regenerateExistingDocuments = async (tramoId: number, request: ReturnType<typeof buildCalculationRequest>, saved: TramoRecord) => {
  const jobs: Promise<Response>[] = [];
  if (saved.has_pdf) {
    jobs.push(fetch(`/api/report/generate?tramo_id=${tramoId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    }));
  }
  if (saved.has_excel) {
    jobs.push(fetch(`/api/report/excel?tramo_id=${tramoId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    }));
  }
  await Promise.all(jobs);
};

const nextAlternativeName = (name: string) => {
  const base = name.replace(/\s+-\s+alternativa\s+\d+$/i, '').trim() || name;
  const match = name.match(/\s+-\s+alternativa\s+(\d+)$/i);
  const next = match ? Number(match[1]) + 1 : 1;
  return `${base} - alternativa ${next}`;
};

const normalizedOptimizedConfig = (config: any, result?: TSCalculationResult | null) => {
  const source = config ?? result?.config ?? {};
  const armLength = source.arm_length ?? source.armLength;
  const tilt = source.tilt ?? source.armTiltAngle;
  return {
    ...source,
    arm_length: armLength,
    armLength,
    tilt,
    armTiltAngle: tilt,
    optic_family: result?.luminaire?.optic_family ?? source.optic_family,
    ldt_id: result?.luminaire?.id ?? source.ldt_id,
    manufacturer: result?.luminaire?.manufacturer ?? source.manufacturer,
    model_family: result?.luminaire?.model_family ?? source.model_family,
    power: source.power ?? result?.luminaire?.power,
    target_flux: result?.luminaire?.flux ?? source.target_flux ?? 0,
    cct: result?.luminaire?.cct ?? source.cct,
    cri: result?.luminaire?.cri ?? source.cri,
    gama: result?.luminaire?.gama ?? source.gama,
    difusor: result?.luminaire?.difusor ?? source.difusor,
    lente: result?.luminaire?.lente ?? source.lente,
    led_type: result?.luminaire?.led_type ?? source.led_type,
  };
};

const optimizedRequestForRow = (row: OptimizationLensResult) => (
  normalizedOptimizedConfig(row.result?.config ?? row.config, row.result)
);

const optimizedResultForRequest = (
  row: OptimizationLensResult,
  request: ReturnType<typeof normalizedOptimizedConfig>,
): TSCalculationResult => ({
  ...(row.result as TSCalculationResult),
  config: request,
});

const TramoEditorPage: React.FC = () => {
  const { projectId: projectIdParam, tramoId: tramoIdParam } = useParams<{ projectId: string; tramoId: string }>();
  const navigate = useNavigate();
  const { authFetch } = useAuth();
  const { t } = useI18n();

  const {
    results,
    loading,
    error,
    ldt_id,
    gama,
    difusor,
    lente,
    led_type,
    setResults,
    setLoading,
    setError,
    setTargetFlux,
    setPower,
    setSpacing,
    setHeight,
    setArmLength,
    setTilt,
    setRoadElements,
    setRoadWidth,
    setSidewalkLeft,
    setSidewalkRight,
    setLanes,
    setMedianWidth,
    setArrangement,
    setPoleOffset,
    setPoleSide,
    setOpticFamily,
    setManufacturer,
    setModelFamily,
    setGama,
    setDifusor,
    setLente,
    setLedType,
    setSelectedLdt,
    setLightingClass,
    setSidewalkLeftClass,
    setSidewalkRightClass,
    setMedianClass,
    setMf,
    setPavement,
    setCct,
    setCri,
    setTAmbC,
    setMargenLavg,
    setIOpMa,
    setLmWMin,
    setDriverEfficiency,
    setIlluminanceScaleMode,
    setIlluminanceScaleMin,
    setIlluminanceScaleMax,
    setPhotometricDisplayUnit,
    setGenerateBuildings,
    setBuildingHeight,
    setBuildingsAsObstacles,
    dirty,
    markSaved,
    setLastEditedTramo,
    setLastOpenedTramo,
    setDirty,
    reset,
  } = useConfigStore();

  const [project, setProject] = useState<ProjectRecord | null>(null);
  const [tramo, setTramo] = useState<TramoRecord | null>(null);
  const [loadingPage, setLoadingPage] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [showSaveOptions, setShowSaveOptions] = useState(false);
  const [savedConfigHash, setSavedConfigHash] = useState<string | null>(null);
  const [lastCalculatedConfigHash, setLastCalculatedConfigHash] = useState<string | null>(null);
  const [lastAutoOptimizationHash, setLastAutoOptimizationHash] = useState<string | null>(null);
  const [wasCalculationPending, setWasCalculationPending] = useState(false);
  const optimizingRef = useRef(false);
  const rerunAutoCalculationRef = useRef(false);
  const autoCalculationAbortRef = useRef<AbortController | null>(null);
  const [autoCalculationRetryTick, setAutoCalculationRetryTick] = useState(0);

  const [batchResults, setBatchResults] = useState<BatchCalculationResponse | null>(null);
  const [excelFile, setExcelFile] = useState<File | null>(null);
  const [optimizationReport, setOptimizationReport] = useState<any>(null);
  const [optimizationLensResults, setOptimizationLensResults] = useState<OptimizationLensResult[] | null>(null);
  const [advancedOptimizationRows, setAdvancedOptimizationRows] = useState<OptimizationLensResult[]>([]);
  const [showAdvancedOptimizationModal, setShowAdvancedOptimizationModal] = useState(false);
  const [showCalculator, setShowCalculator] = useState(false);

  const projectId = projectIdParam ? Number(projectIdParam) : null;
  const isNew = tramoIdParam === undefined || tramoIdParam.toLowerCase() === 'new';
  const parsedTramoId = !isNew && tramoIdParam ? Number(tramoIdParam) : null;
  const tramoId = parsedTramoId && Number.isInteger(parsedTramoId) && parsedTramoId > 0 ? parsedTramoId : null;

  // Subscribe shallow to the fields that compose the calculation request so
  // unrelated store changes (e.g. `dirty`, `loading`) don't invalidate the
  // memoised hashes below.
  const requestSnapshot = useConfigStore(useShallow(requestSnapshotSelector));
  const request = useMemo(() => buildCalculationRequest(), [requestSnapshot]);
  const currentConfigHash = useMemo(() => configHash(request), [request]);
  const currentAutoOptimizationHash = useMemo(() => autoOptimizationConfigHash(request), [request]);

  const dirtyConfig = currentConfigHash !== savedConfigHash;
  const needsCalculation = currentAutoOptimizationHash !== lastAutoOptimizationHash;
  const hasTemporaryResults = dirtyConfig && !needsCalculation;
  const calculatedPendingSave = wasCalculationPending && !needsCalculation && Boolean(results);
  const hasLuminaireForCalculation = Boolean(ldt_id);

  const guard = useUnsavedChangesGuard({
    isDirty: () => dirtyConfig || calculatedPendingSave,
    isStale: () => needsCalculation,
  });

  // Auto-calculate on config change with debounce. Keep it a calculation,
  // not a hidden optimization, so results match the configured DIALux case.
  useEffect(() => {
    if (loadingPage || !hasLuminaireForCalculation || excelFile) return;
    if (!dirty && !wasCalculationPending && !needsCalculation) return;
    // ponytail: if a config changed mid-flight we must honor the queued rerun
    // even when the hash now matches a previously calculated state.
    if (!needsCalculation && !rerunAutoCalculationRef.current) return;
    if (optimizingRef.current) {
      rerunAutoCalculationRef.current = true;
      autoCalculationAbortRef.current?.abort();
      return;
    }

    const timer = setTimeout(async () => {
      const abortController = new AbortController();
      autoCalculationAbortRef.current = abortController;
      optimizingRef.current = true;
      rerunAutoCalculationRef.current = false;
      try {
        const beforeConfig = buildCalculationRequest();
        const startedAutoOptimizationHash = autoOptimizationConfigHash(beforeConfig);

        const calcBody = {
          ...beforeConfig,
          target_flux: (beforeConfig.target_flux ?? 0) > 0 ? beforeConfig.target_flux : null,
        };
        const calculatedHash = calculationConfigHash(calcBody);
        const response = await fetch('/api/calculate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(calcBody),
          signal: abortController.signal,
        });

        if (!response.ok) {
          const errData = await response.json().catch(() => null);
          throw new Error(errData?.detail || `Calculation failed (HTTP ${response.status})`);
        }

        const result = await response.json();
        if (autoOptimizationConfigHash(buildCalculationRequest()) !== startedAutoOptimizationHash) {
          rerunAutoCalculationRef.current = true;
          return;
        }

        const updates: Record<string, any> = {
          results: result,
          dirty: true,
        };
        const resultConfig = result?.config as Record<string, any> | undefined;
        const finalFlux = resultConfig?.target_flux;
        const finalPower = resultConfig?.power;
        if (typeof finalFlux === 'number' && Number.isFinite(finalFlux)) updates.target_flux = finalFlux;
        if (typeof finalPower === 'number' && Number.isFinite(finalPower)) updates.power = finalPower;
        useConfigStore.setState(updates);
        setLastCalculatedConfigHash(calculatedHash);
        setLastAutoOptimizationHash(startedAutoOptimizationHash);
      } catch (err: any) {
        if (err?.name === 'AbortError') return;
        setError(err.message || t('errors.calculateError'));
      } finally {
        if (autoCalculationAbortRef.current === abortController) {
          autoCalculationAbortRef.current = null;
        }
        optimizingRef.current = false;
        if (rerunAutoCalculationRef.current) {
          setAutoCalculationRetryTick((tick) => tick + 1);
        }
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [
    autoCalculationRetryTick,
    excelFile,
    hasLuminaireForCalculation,
    loadingPage,
    dirty,
    needsCalculation,
    wasCalculationPending,
    currentAutoOptimizationHash,
    t,
  ]);

  const loadTramo = useCallback(async () => {
    if (!projectId) return;
    setLoadingPage(true);
    setLoadError(null);
    try {
      const proj = await getProject(authFetch, projectId);
      setProject(proj);
      setTAmbC(proj.t_amb_c ?? 25);
      setMargenLavg(proj.margen_lavg ?? 0);
      setIOpMa(proj.i_op_ma ?? null);
      setLmWMin(proj.lm_w_min ?? null);
      if (!isNew) {
        if (!tramoId) throw new Error('Tramo inválido');
        const tr = await getTramo(authFetch, projectId, tramoId);
        setTramo(tr);
        reset();
        applyTramoConfig(tr, {
          setRoadElements,
          setRoadWidth,
          setSidewalkLeft,
          setSidewalkRight,
          setLanes,
          setMedianWidth,
          setArrangement,
          setHeight,
          setSpacing,
          setArmLength,
          setPoleOffset,
          setPoleSide,
          setTilt,
          setOpticFamily,
          setTargetFlux,
          setPower,
          setManufacturer,
          setModelFamily,
          setGama,
          setDifusor,
          setLente,
          setLedType,
              setSelectedLdt,
              setLightingClass,
              setSidewalkLeftClass,
              setSidewalkRightClass,
              setMedianClass,
              setMf,
              setPavement,
              setCct,
              setCri,
              setTAmbC,
              setMargenLavg,
              setIOpMa,
              setLmWMin,
              setDriverEfficiency,
              setIlluminanceScaleMode,
              setIlluminanceScaleMin,
              setIlluminanceScaleMax,
          setPhotometricDisplayUnit,
          setGenerateBuildings,
          setBuildingHeight,
          setBuildingsAsObstacles,
          setResults,
        });
        const snap: SavedSnapshot = {
          configJson: tr.config_json ?? snapshotConfig().configJson,
          resultJson: tr.result_json ?? null,
        };
        markSaved(snap);
        const loadedRequest = buildCalculationRequest();
        setSavedConfigHash(configHash(loadedRequest));
        setLastCalculatedConfigHash(calculationConfigHash(loadedRequest));
        // ponytail: align the auto-optimization hash with the current config
        // so the effect does NOT fire on load.  The user can still trigger
        // a recalculation by editing a field or clicking the "Calcular" button.
        setLastAutoOptimizationHash(autoOptimizationConfigHash(loadedRequest));
        setWasCalculationPending(false);
        setLastEditedTramo(null);
        setLastOpenedTramo(projectId, tr.id);
      } else {
        // The "new tramo" flow now lives on the project list page: a modal
        // collects the name, the tramo is created with default config, and
        // the user is navigated to its editor. If we somehow land on this
        // route (e.g. by typing the URL), just bounce back to the project
        // list so the editor never opens in an unsaved state.
        navigate(`/projects/${projectId}`, { replace: true });
        return;
      }
    } catch (err: any) {
      setLoadError(err.message || t('errors.unknown'));
    } finally {
      setLoadingPage(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, tramoId, isNew, authFetch, t, setDirty]);

  useEffect(() => {
    loadTramo();
  }, [loadTramo]);

  const saveTramo = useCallback(async (resultOverride?: TSCalculationResult | null): Promise<TramoRecord | null> => {
    if (saving) return null;
    if (!projectId) return null;
    setSaveMessage(null);
    const request = buildCalculationRequest();
    const hash = configHash(request);
    const calcHash = calculationConfigHash(request);
    const body: Record<string, any> = {
      config_json: withHash(request, hash),
      result_json: (resultOverride ?? results) ? withHash(resultOverride ?? results, calcHash) : null,
    };
    if (isNew) {
      body.name = tramo?.name?.trim() || 'Tramo';
    }
    setSaving(true);
    try {
      let saved: TramoRecord;
      if (isNew) {
        saved = await createTramo(authFetch, projectId, body);
        setTramo(saved);
      } else {
        if (!tramoId) return null;
        saved = await updateTramo(authFetch, projectId, tramoId, body);
        await regenerateExistingDocuments(tramoId, request, saved);
        setTramo(saved);
      }
      const snap: SavedSnapshot = {
        configJson: saved.config_json ?? body.config_json,
        resultJson: saved.result_json ?? body.result_json,
      };
      markSaved(snap);
      setLastCalculatedConfigHash((resultOverride ?? results) ? calcHash : null);
      setLastAutoOptimizationHash(resultOverride ?? results ? autoOptimizationConfigHash(request) : null);
      setSavedConfigHash(hash);
      setWasCalculationPending(false);
      setLastEditedTramo(saved.id);
      setSaveMessage(t('tramoEditor.saveMessage'));
      if (isNew) {
        guard.bypass();
        navigate(`/projects/${projectId}/tramos/${saved.id}`, { replace: true });
      }
      return saved;
    } catch (err: any) {
      setSaveMessage(`Error: ${err.message || t('errors.unknown')}`);
      return null;
    } finally {
      setSaving(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [saving, projectId, tramoId, isNew, tramo, results, authFetch, t, markSaved, setLastEditedTramo, setLastOpenedTramo, guard, navigate]);

  const handleExcelFileChange = (file: File | null) => {
    setExcelFile(file);
    setBatchResults(null);
    setResults(null);
    setError(null);
    setOptimizationReport(null);
    setOptimizationLensResults(null);
    setShowAdvancedOptimizationModal(false);
    setAdvancedOptimizationRows([]);
  };

  const calculateExcel = async (file: File) => {
    setLoading(true);
    setError(null);
    setBatchResults(null);
    setResults(null);
    setOptimizationReport(null);
    setOptimizationLensResults(null);
    setShowAdvancedOptimizationModal(false);
    setAdvancedOptimizationRows([]);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const response = await fetch('/api/batch-excel', {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => null);
        throw new Error(errData?.detail || t('errors.excelCalculation'));
      }
      setBatchResults(await response.json());
    } catch (err: any) {
      setError(err.message || t('errors.excelCalculation'));
    } finally {
      setLoading(false);
    }
  };

  const optimizeAdvanced = async (
    variables: AdvancedOptimizationVariables,
    objective: AdvancedOptimizationObjective,
    opticFamilies: string[],
    limits: AdvancedOptimizationLimits = {},
  ) => {
    setLoading(true);
    setError(null);
    setBatchResults(null);
    setExcelFile(null);
    setOptimizationReport(null);
    setOptimizationLensResults(null);
    setShowAdvancedOptimizationModal(false);
    setAdvancedOptimizationRows([]);
    const beforeConfig = buildCalculationRequest();
    try {
      const isLensBatch = variables.optic_family;
      const response = await fetch(isLensBatch ? '/api/optimize/advanced-batch' : '/api/optimize/advanced', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config: beforeConfig, variables, limits, objective, optic_families: opticFamilies }),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => null);
        throw new Error(errData?.detail || t('errors.optimizeSetup'));
      }
      if (isLensBatch) {
        const batch = await response.json() as BatchCalculationResponse;
        const lensRows: OptimizationLensResult[] = batch.items.map(item => ({
          model_id: item.model_id,
          optic_family: item.config?.optic_family ?? item.result?.luminaire.optic_family ?? item.model_id.split(' ').pop() ?? item.model_id,
          feasible: Boolean(item.config && item.result && !item.error),
          message: item.error,
          config: item.result ? optimizedRequestForRow({ config: item.config, result: item.result } as OptimizationLensResult) : item.config,
          result: item.result,
          changes: item.config ? buildOptimizationChanges(beforeConfig, item.config) : [],
        }));
        const firstFeasible = lensRows.find(item => item.feasible && item.result);
        setOptimizationLensResults(lensRows);
        setAdvancedOptimizationRows(lensRows);
        setShowAdvancedOptimizationModal(true);
        setOptimizationReport({
          feasible: Boolean(firstFeasible),
          message: firstFeasible ? t('results.optimized') : t('results.notFeasible'),
          objective,
          checked: 0,
          changes: [],
        });
        return;
      }
      const data = await response.json() as OptimizationResponse;
      const row: OptimizationLensResult = {
        model_id: data.config?.optic_family ?? data.result?.luminaire?.optic_family ?? t('optimize.advanced'),
        optic_family: data.config?.optic_family ?? data.result?.luminaire?.optic_family ?? t('optimize.advanced'),
        feasible: Boolean(data.feasible && data.config && data.result),
        message: data.message,
        config: data.result ? optimizedRequestForRow({ config: data.config, result: data.result } as OptimizationLensResult) : data.config,
        result: data.result,
        changes: buildOptimizationChanges(beforeConfig, data.config ?? data.result?.config ?? beforeConfig),
      };
      setAdvancedOptimizationRows([row]);
      setShowAdvancedOptimizationModal(true);
      setOptimizationReport(buildOptimizationReport(beforeConfig, data));
    } catch (err: any) {
      setError(err.message || t('errors.optimizeSetup'));
    } finally {
      setLoading(false);
    }
  };

  const handleSaveClick = async () => {
    if (!dirtyConfig && !calculatedPendingSave) {
      setSaveMessage(t('tramoEditor.noChanges'));
      return;
    }
    if (isNew) {
      const proceed = await guard.confirmSaveWithoutRecalc();
      if (!proceed) return;
      await saveTramo(results as TSCalculationResult | null);
      return;
    }
    setSaveMessage(null);
    setShowSaveOptions(true);
  };

  const closeSaveOptions = () => {
    if (saving) return;
    setShowSaveOptions(false);
  };

  const handleConfirmSaveReplaceCurrent = async () => {
    setShowSaveOptions(false);
    const proceed = await guard.confirmSaveWithoutRecalc();
    if (!proceed) return;
    await saveTramo(results as TSCalculationResult | null);
  };

  const handleConfirmSaveAlternative = async () => {
    if (!projectId || saving) return;
    setShowSaveOptions(false);
    const proceed = await guard.confirmSaveWithoutRecalc();
    if (!proceed) return;
    setSaving(true);
    try {
      const request = buildCalculationRequest();
      const hash = configHash(request);
      const calcHash = calculationConfigHash(request);
      const saved = await createTramo(authFetch, projectId, {
        parent_section_id: tramo?.parent_section_id ?? tramo?.id ?? tramoId ?? undefined,
        config_json: withHash(request, hash),
        result_json: results ? withHash(results, calcHash) : null,
      });
      markSaved({ configJson: saved.config_json ?? withHash(request, hash), resultJson: saved.result_json ?? null });
      setLastEditedTramo(saved.id);
      setSavedConfigHash(hash);
      setLastCalculatedConfigHash(results ? calcHash : null);
      setLastAutoOptimizationHash(results ? autoOptimizationConfigHash(request) : null);
      setTramo(saved);
      setWasCalculationPending(false);
      setSaveMessage(t('tramoEditor.saveMessage'));
    } finally {
      setSaving(false);
    }
  };

  const applyOptimizationRowToEditor = (row: OptimizationLensResult, request: any) => {
    const luminaire = row.result?.luminaire;
    if (typeof request.power === 'number') setPower(request.power);
    if (typeof request.target_flux === 'number') setTargetFlux(request.target_flux);
    if (typeof request.cct === 'number') setCct(request.cct);
    if (typeof request.cri === 'number') setCri(request.cri);
    if (typeof request.spacing === 'number') setSpacing(request.spacing);
    if (typeof request.height === 'number') setHeight(request.height);
    if (typeof request.arm_length === 'number') setArmLength(request.arm_length);
    if (typeof request.tilt === 'number') setTilt(request.tilt);
    if (request.optic_family) setOpticFamily(request.optic_family);
    if (request.manufacturer) setManufacturer(request.manufacturer);
    if (request.model_family) setModelFamily(request.model_family);
    if (request.gama !== undefined) setGama(request.gama || '');
    if (request.difusor !== undefined) setDifusor(request.difusor || '');
    if (request.lente !== undefined) setLente(request.lente || '');
    if (request.led_type !== undefined) setLedType(request.led_type || '');
    if (request.ldt_id || luminaire) {
      setSelectedLdt({
        id: request.ldt_id || luminaire?.id || '',
        manufacturer: request.manufacturer || luminaire?.manufacturer || '',
        model_family: request.model_family || luminaire?.model_family || '',
        optic_family: request.optic_family || luminaire?.optic_family || '',
      });
    }
    if (row.result) setResults(row.result);
  };

  const persistAdvancedOptimizationRow = async (row: OptimizationLensResult, mode: 'alternative' | 'replace') => {
    if (!projectId || saving || !row.config || !row.result) return;
    const request = optimizedRequestForRow(row);
    const resultToSave = optimizedResultForRequest(row, request);

    // apply the row to the editor state BEFORE computing the hash,
    // so configHash(buildCalculationRequest()) matches currentConfigHash
    // (normalizedOptimizedConfig reorders fields, causing hash mismatch)
    applyOptimizationRowToEditor({ ...row, result: resultToSave }, request);
    // Reset dirty so the flux-detail async callback does NOT overwrite
    // the optimized config values (power, etc.) with catalog defaults.
    useConfigStore.setState({ dirty: false });
    const hash = configHash(buildCalculationRequest());
    const calcHash = calculationConfigHash(buildCalculationRequest());

    if (mode === 'replace') {
      setLastCalculatedConfigHash(calcHash);
      setLastAutoOptimizationHash(autoOptimizationConfigHash(buildCalculationRequest()));
      setWasCalculationPending(false);
      setShowAdvancedOptimizationModal(false);
      return;
    }

    const body = {
      config_json: withHash(request, hash),
      result_json: withHash(resultToSave, calcHash),
    };
    setSaving(true);
    setSaveMessage(null);
    try {
      const saved = await createTramo(authFetch, projectId, {
        parent_section_id: tramo?.parent_section_id ?? tramo?.id ?? tramoId ?? undefined,
        ...body,
      });

      markSaved({ configJson: saved.config_json ?? body.config_json, resultJson: saved.result_json ?? body.result_json });
      setLastEditedTramo(saved.id);
      setSavedConfigHash(hash);
      setLastCalculatedConfigHash(calcHash);
      setLastAutoOptimizationHash(autoOptimizationConfigHash(buildCalculationRequest()));
      setWasCalculationPending(false);
      setTramo(saved);
      setShowAdvancedOptimizationModal(false);
      setSaveMessage(t('tramoEditor.saveMessage'));
    } catch (err: any) {
      setSaveMessage(`Error: ${err.message || t('errors.unknown')}`);
    } finally {
      setSaving(false);
    }
  };

  const handleRecalcPromptCalculateFirst = async () => {
    guard.state.resolveRecalcPrompt?.(false);
    if (excelFile) {
      await calculateExcel(excelFile);
    }
  };

  const handleNavigateToList = async () => {
    if (!dirtyConfig && !calculatedPendingSave) {
      navigate(`/projects/${projectId}`);
      return;
    }
    const proceed = await guard.confirmNavigation();
    if (proceed) {
      navigate(`/projects/${projectId}`);
    }
  };

  const handleUnsavedSaveAndExit = async () => {
    if (calculatedPendingSave) {
      const saved = await saveTramo(results as TSCalculationResult | null);
      if (saved) {
        guard.bypass();
        navigate(`/projects/${projectId}`);
      }
      return;
    }
    if (excelFile) {
      await calculateExcel(excelFile);
    }
    guard.state.resolveNavigation?.(false);
  };

  const handleReplaceAndExit = async () => {
    const saved = await saveTramo(results as TSCalculationResult | null);
    if (saved) {
      guard.bypass();
      navigate(`/projects/${projectId}`);
    }
  };

  const handleSaveAlternativeAndExit = async () => {
    if (!projectId || saving) return;
    const request = buildCalculationRequest();
    const hash = configHash(request);
    const calcHash = calculationConfigHash(request);
    setSaving(true);
    try {
      const saved = await createTramo(authFetch, projectId, {
        parent_section_id: tramo?.parent_section_id ?? tramo?.id ?? tramoId ?? undefined,
        config_json: withHash(request, hash),
        result_json: results ? withHash(results, calcHash) : null,
      });
      markSaved({ configJson: saved.config_json ?? withHash(request, hash), resultJson: saved.result_json ?? null });
      setLastEditedTramo(saved.id);
      setSavedConfigHash(hash);
      setLastCalculatedConfigHash(results ? calcHash : null);
      setLastAutoOptimizationHash(results ? autoOptimizationConfigHash(request) : null);
      guard.bypass();
      navigate(`/projects/${projectId}`);
    } finally {
      setSaving(false);
    }
  };

  const handleUnsavedDiscard = () => {
    guard.bypass();
    reset();
    setLastEditedTramo(null);
    navigate(`/projects/${projectId}`);
  };

  const handleTramoNameSave = async (next: string) => {
    if (!projectId) return;
    if (isNew) {
      // Should be unreachable: the editor is never mounted for a brand-new
      // tramo anymore. If we ever do land here, do nothing rather than mutate
      // a non-existent record.
      return;
    }
    if (!tramoId) return;
    const updated = await updateTramo(authFetch, projectId, tramoId, { name: next });
    setTramo(updated);
  };

  if (loadingPage) {
    return (
      <main className="p-6">
        <div className="mx-auto max-w-7xl">
          <div className="rounded-xl border border-[#E8E2D8] bg-[#FFFFFF] p-12 text-center text-[#6a6a6a]">
            {t('actions.loading')}
          </div>
        </div>
      </main>
    );
  }

  if (loadError || !project) {
    return (
      <main className="p-6">
        <div className="mx-auto max-w-3xl text-center">
          <div className="rounded-xl border border-[#B42318]/25 bg-[#FDECEA] p-8">
            <p className="text-[#B42318]">{loadError || t('projects.editor.notFound')}</p>
            <button
              type="button"
              onClick={() => navigate('/projects')}
              className="mt-4 rounded-lg bg-[#1E1E1E] px-4 py-2 text-sm font-semibold text-white hover:bg-[#333333]"
            >
              {t('projects.editor.backToList')}
            </button>
          </div>
        </div>
      </main>
    );
  }

  const currentTramoName = (isNew ? (tramo?.name ?? 'Tramo') : (tramo?.name ?? 'Tramo')).trim() || 'Tramo';
  // ponytail: only flag "needs calculation" when there is genuinely nothing
  // to show — i.e. a brand-new tramo with a luminaire picked but no result
  // yet.  For an already-saved tramo we keep the saved result on screen and
  // report "Actualizado" because the user hasn't actually changed anything.
  const resultIsStale = hasLuminaireForCalculation && !results;
  const statusLabel = calculatedPendingSave
    ? t('tramoEditor.statusCalculatedPendingSave')
    : dirtyConfig
      ? (needsCalculation ? t('tramoEditor.statusNeedsCalculation') : t('tramoEditor.statusCalculatedUnsaved'))
      : resultIsStale
        ? t('tramoEditor.statusNeedsCalculation')
        : t('tramoEditor.statusUpdated');
  const statusTone = (needsCalculation || resultIsStale) ? 'danger' : dirtyConfig || calculatedPendingSave ? 'warning' : 'success';

  return (
    <main className="tramo-studio h-[calc(100vh-4rem)] overflow-hidden px-3 py-3 text-[#1E1E1E] sm:px-4 lg:px-5">
      <div className="mx-auto flex h-full w-full max-w-[1920px] flex-col overflow-hidden">
        <div className="mb-3 flex flex-shrink-0 flex-col gap-3 rounded-xl border border-[#E8E2D8]/80 bg-[#FFFFFF]/85 px-3 py-2 shadow-[0_18px_48px_rgba(0,0,0,0.35)] backdrop-blur sm:flex-row sm:items-center sm:justify-between">
          <nav className="flex min-w-0 items-center gap-2 text-sm text-[#A09A91]">
            <Link to="/projects" className="font-semibold text-[#1E1E1E] hover:text-[#333333]">
              {t('projects.title')}
            </Link>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6" />
            </svg>
            <button
              type="button"
              onClick={handleNavigateToList}
              className="truncate font-semibold text-[#1E1E1E] hover:text-[#333333]"
              title={project.project_name}
            >
              {project.project_name}
            </button>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6" />
            </svg>
            <TramoNameInput
              value={currentTramoName}
              onSave={handleTramoNameSave}
              placeholder={t('tramoEditor.namePlaceholder')}
              compact
            />
          </nav>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowCalculator(true)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[#E8E2D8] bg-[#FFFFFF] px-2.5 py-1.5 text-[11px] font-semibold text-[#6A6A6A] hover:bg-[#F7F4EF] hover:text-[#1E1E1E]"
              title="Comprobación de cálculos"
            >
              <Calculator className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Calcular</span>
            </button>
            <div className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${statusTone === 'danger' ? 'border-[#B42318]/25 bg-[#FDECEA] text-[#B42318]' : statusTone === 'warning' ? 'border-[#B7791F]/25 bg-[#F5EDE0] text-[#B7791F]' : 'border-[#1F7A4D]/25 bg-[#1F7A4D]/10 text-[#1F7A4D]'}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${statusTone === 'danger' ? 'bg-red-500' : statusTone === 'warning' ? 'bg-amber-500' : 'bg-emerald-500'}`} />
              {statusLabel}
            </div>
            {saveMessage && (
              <span
                className={`text-xs font-medium ${
                  saveMessage.startsWith('Error') ? 'text-[#B42318]' : 'text-[#1F7A4D]'
                }`}
              >
                {saveMessage}
              </span>
            )}
          </div>
        </div>

        {error && (
          <div className="mb-6 max-w-2xl rounded-lg border border-[#B42318]/25 bg-[#FDECEA] p-4">
            <div className="flex items-center gap-2">
              <svg className="h-5 w-5 flex-shrink-0 text-[#B42318]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="15" y1="9" x2="9" y2="15" />
                <line x1="9" y1="9" x2="15" y2="15" />
              </svg>
              <p className="text-sm text-[#B42318]">{error}</p>
            </div>
          </div>
        )}

        <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-hidden lg:grid-cols-[19rem_minmax(0,1fr)_19rem] xl:grid-cols-[21rem_minmax(0,1fr)_21rem] 2xl:grid-cols-[22rem_minmax(0,1fr)_22rem]">
          <section className="min-h-0 space-y-3 overflow-y-auto pr-1 lg:self-start">
            <ConfigurationTabsPanel />
          </section>

          <section className="min-h-0 space-y-3 overflow-hidden">
            <RoadViewContainer />
            {batchResults && (
              <BatchResultsPanel batch={batchResults} />
            )}
          </section>

          <section className="min-h-0 space-y-3 overflow-y-auto pr-1">
            <QuickInfoPanel
              result={results}
              loading={loading}
              tramoId={tramoId ?? undefined}
              projectName={project.project_name}
              needsCalculation={needsCalculation}
              onDocumentSaved={() => {
                if (!isNew && projectId && tramoId) {
                  getTramo(authFetch, projectId, tramoId)
                    .then(setTramo)
                    .catch(() => undefined);
                }
              }}
            />
            <div className="flex flex-col gap-2">
              <button
                type="button"
                onClick={handleSaveClick}
                disabled={saving || loading}
                className={`flex w-full items-center justify-center rounded-lg border px-4 py-3 text-sm font-bold shadow-sm transition-all ${
                  saving || loading
                    ? 'cursor-not-allowed border-[#E8E2D8] bg-[#F0EDE8] text-[#6a6a6a]'
                    : 'border-[#D4CEC6] bg-[#FFFFFF] text-[#6A6A6A] hover:bg-[#F7F4EF] active:bg-[#F0EDE8]'
                }`}
              >
                {saving ? t('form.saving') : t('actions.save')}
              </button>
              {!excelFile && !hasLuminaireForCalculation && (
                <p className="text-xs text-[#B42318] text-center">
                  {t('tramoEditor.missingLuminaireParams')}
                </p>
              )}
            </div>
            <AutoOptimizePanel loading={loading} onRunAdvanced={optimizeAdvanced} />
          </section>
        </div>
      </div>

      <UnsavedChangesModal
        open={guard.state.blocking}
        saving={saving}
        calculated={hasTemporaryResults || calculatedPendingSave}
        pendingSaveOnly={calculatedPendingSave}
        canSaveAlternative={!tramo?.parent_section_id}
        onSaveAndExit={handleUnsavedSaveAndExit}
        onReplaceAndExit={handleReplaceAndExit}
        onSaveAlternativeAndExit={handleSaveAlternativeAndExit}
        onDiscard={handleUnsavedDiscard}
        onCancel={() => guard.state.resolveNavigation?.(false)}
      />
      <RecalcPromptModal
        open={guard.state.requireRecalcPrompt}
        onSaveAnyway={() => guard.state.resolveRecalcPrompt?.(true)}
        onCalculateFirst={handleRecalcPromptCalculateFirst}
        onCancel={() => guard.state.resolveRecalcPrompt?.(false)}
      />
      <SaveOptionsModal
        open={showSaveOptions}
        saving={saving}
        canSaveAlternative={!tramo?.parent_section_id}
        onSaveAlternative={handleConfirmSaveAlternative}
        onReplaceCurrent={handleConfirmSaveReplaceCurrent}
        onCancel={closeSaveOptions}
      />
      <AdvancedOptimizationResultsModal
        open={showAdvancedOptimizationModal}
        rows={advancedOptimizationRows}
        saving={saving}
        canSaveAlternative={!tramo?.parent_section_id}
        onSaveAlternative={(row) => persistAdvancedOptimizationRow(row, 'alternative')}
        onReplaceCurrent={(row) => persistAdvancedOptimizationRow(row, 'replace')}
        onClose={() => {
          if (!saving) setShowAdvancedOptimizationModal(false);
        }}
      />
      <CalculatorModal
        open={showCalculator}
        onClose={() => setShowCalculator(false)}
      />
    </main>
  );
};

export default TramoEditorPage;
