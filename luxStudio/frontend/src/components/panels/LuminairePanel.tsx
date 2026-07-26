import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useConfigStore } from '../../store/useConfigStore';
import type { FluxDetail, LDTInfo, PcbOption } from '../../types';
import EditableSlider from '../ui/EditableSlider';
import { useI18n } from '../../i18n';
import ArrangementPanel from './ArrangementPanel';

interface DimensionOption { id: number; name: string; eficiencia?: number | null; }
interface ValidCombo { gama: string; difusor: string; lente: string; led_type: string | null; }
interface DimensionsData {
  gamas: DimensionOption[];
  difusores: DimensionOption[];
  lentes: DimensionOption[];
  led_types: DimensionOption[];
  valid_combinations: ValidCombo[];
  // Power cap map keyed by "GAMA|DIFUSOR|LENTE|LED_TYPE" (upper-cased,
  // pipe-joined).  Missing key ⇒ no cap known for that 4-tuple.
  pmax_by_combo?: Record<string, number>;
  pmax_source_by_combo?: Record<string, 'exact' | 'led_type_fallback' | string>;
}

const unique = <T,>(values: T[]) => Array.from(new Set(values)).filter(Boolean).sort();

type LuminairePanelProps = {
  embedded?: boolean;
};

const LuminairePanel: React.FC<LuminairePanelProps> = ({ embedded = false }) => {
  const { t } = useI18n();
  const {
    optic_family, setOpticFamily, target_flux, setTargetFlux, power, setPower, cct, setCct,
    cri, setCri,
    manufacturer, setManufacturer, model_family, setModelFamily,
    ldt_id, setSelectedLdt, setDirty,
    gama, setGama, difusor, setDifusor, lente, setLente,
    led_type, setLedType,
    height, setHeight,
    arm_length, setArmLength,
    tilt, setTilt,
    t_amb_c: tAmbC,
    i_op_ma: iOpMa,
    lm_w_min: lmWMin,
    driverEfficiency, setDriverEfficiency,
  } = useConfigStore();

  const [catalog, setCatalog] = useState<LDTInfo[]>([]);
  const [dims, setDims] = useState<DimensionsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [externalLdt, setExternalLdt] = useState<LDTInfo | null>(null);
  const [uploadingExternal, setUploadingExternal] = useState(false);
  const [externalError, setExternalError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [fluxDetail, setFluxDetail] = useState<FluxDetail | null>(null);
  const [availablePcbs, setAvailablePcbs] = useState<PcbOption[]>([]);
  const [selectedPcbRef, setSelectedPcbRef] = useState<string>('');
  const [noPcbWarning, setNoPcbWarning] = useState(false);
  const [driverEffDraft, setDriverEffDraft] = useState('90,0');
  const [driverEffFocused, setDriverEffFocused] = useState(false);

  useEffect(() => {
    if (!driverEffFocused) {
      setDriverEffDraft((driverEfficiency * 100).toFixed(1).replace('.', ','));
    }
  }, [driverEfficiency, driverEffFocused]);

  const commitDriverEff = (raw: string) => {
    const v = parseFloat(raw.replace(',', '.'));
    if (!isNaN(v)) setDriverEfficiency(Math.min(100, Math.max(50, v)) / 100);
  };

  const loadCatalog = () => {
    setLoading(true);
    Promise.all([
      fetch('/api/ldt/catalog').then(r => r.json()),
      fetch('/api/ldt/dimensions').then(r => r.json()),
    ])
      .then(([cat, d]) => {
        setCatalog(Array.isArray(cat) ? cat : []);
        setDims(d);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadCatalog(); }, []);

  // --- Symmetric dimension options from valid_combinations ---

  const validCombos = useMemo(() => dims?.valid_combinations || [], [dims]);

  const matchesSelection = (
    vc: ValidCombo,
    except: 'gama' | 'difusor' | 'lente' | 'led_type',
  ) => (
    (except === 'gama' || !gama || vc.gama === gama) &&
    (except === 'difusor' || !difusor || vc.difusor === difusor) &&
    (except === 'lente' || !lente || vc.lente === lente) &&
    (except === 'led_type' || !led_type || vc.led_type === led_type)
  );

  const gamas = useMemo(() => {
    if (!dims?.gamas) return [];
    if (!difusor && !lente && !led_type) return dims.gamas.map(g => g.name);
    const valid = new Set(validCombos.filter(vc => matchesSelection(vc, 'gama')).map(vc => vc.gama));
    return dims.gamas.filter(g => valid.has(g.name)).map(g => g.name);
  }, [dims, validCombos, difusor, lente, led_type]);

  const difusores = useMemo(() => {
    if (!dims?.difusores) return [];
    if (!gama && !lente && !led_type) return dims.difusores.map(d => d.name);
    const valid = new Set(validCombos.filter(vc => matchesSelection(vc, 'difusor')).map(vc => vc.difusor));
    return dims.difusores.filter(d => valid.has(d.name)).map(d => d.name);
  }, [dims, validCombos, gama, lente, led_type]);

  const lentes = useMemo(() => {
    if (!dims?.lentes) return [];
    if (!gama && !difusor && !led_type) return dims.lentes.map(l => l.name);
    const valid = new Set(validCombos.filter(vc => matchesSelection(vc, 'lente')).map(vc => vc.lente));
    return dims.lentes.filter(l => valid.has(l.name)).map(l => l.name);
  }, [dims, validCombos, gama, difusor, led_type]);

  const ledTypes = useMemo(() => {
    if (!dims?.led_types) return [];
    if (!gama && !difusor && !lente) return dims.led_types.map(lt => lt.name);
    const valid = new Set(validCombos.filter(vc => matchesSelection(vc, 'led_type')).map(vc => vc.led_type).filter(Boolean));
    return dims.led_types.filter(lt => valid.has(lt.name)).map(lt => lt.name);
  }, [dims, validCombos, gama, difusor, lente]);

  // --- Find reference LDT matching the current selection ---

  // Pre-build a Map<"GAMA|DIFUSOR|LENTE|LED_TYPE", LDTInfo> so reference
  // lookups are O(1) instead of scanning the whole catalog on every change.
  const catalogIndex = useMemo(() => {
    const map = new Map<string, LDTInfo>();
    for (const item of catalog) {
      const key = [item.gama, item.difusor, item.lente, item.led_type ?? '']
        .map(s => (s ?? '').toString().trim().toUpperCase())
        .join('|');
      map.set(key, item);
    }
    return map;
  }, [catalog]);

  const referenceLdt = useMemo(() => {
    if (!gama || !difusor || !lente) return null;

    const candidates = catalog.filter(i =>
      i.gama === gama &&
      i.difusor === difusor &&
      i.lente === lente
    );
    const selectableLedTypes = unique(candidates.map(i => i.led_type).filter(Boolean));
    if (!led_type && selectableLedTypes.length > 0) return null;

    if (led_type) {
      const key = [gama, difusor, lente, led_type]
        .map(s => (s ?? '').toString().trim().toUpperCase())
        .join('|');
      return catalogIndex.get(key) ?? null;
    }

    return candidates.find(i => !i.led_type) || null;
  }, [catalog, catalogIndex, gama, difusor, lente, led_type]);

  // --- Power cap (Pmax) for the current 4-tuple ---
  // The catalog serves a precomputed map of (gama, difusor, lente, led_type)
  // -> pmax_ajustada.  When the 4-tuple is complete, we look it up and
  // use the value as the slider's `max`.  The backend also enforces
  // the cap on /api/calculate, so even if a tampered request reaches
  // the server the calculation is rejected.
  const pmaxKey = useMemo(() => {
    if (!gama || !difusor || !lente) return null;
    return [gama, difusor, lente, led_type || '']
      .map(s => s.trim().toUpperCase())
      .join('|');
  }, [gama, difusor, lente, led_type]);

  const pmax = useMemo(() => {
    if (!pmaxKey) return null;
    if (!dims?.pmax_by_combo) return null;
    const value = dims.pmax_by_combo[pmaxKey];
    return typeof value === 'number' && Number.isFinite(value) ? value : null;
  }, [dims, pmaxKey]);

  const pmaxUsesFallback = useMemo(() => {
    if (!pmaxKey || !dims?.pmax_source_by_combo) return false;
    return dims.pmax_source_by_combo[pmaxKey] === 'led_type_fallback';
  }, [dims, pmaxKey]);

  // Power is now computed from target_flux via the flux-detail endpoint.
  // The pmax cap is enforced by showing a warning when p_total > pmax.
  // This effect ensures legacy tramos restore a sensible target_flux from saved power.
  useEffect(() => {
    if (pmax === null || pmaxKey === null) return;
    const state = useConfigStore.getState();
    if (!state.target_flux && state.power > 0) {
      const ldtEfficacy = referenceLdt && referenceLdt.power > 0
        ? referenceLdt.flux / referenceLdt.power
        : 130;
      setTargetFlux(state.power * ldtEfficacy);
    }
  }, [pmaxKey, pmax, referenceLdt?.id]);

  // --- Automatic updates should not mark a clean tramo as dirty ---

  const applyAutomaticCatalogUpdate = (update: () => void) => {
    const wasDirty = useConfigStore.getState().dirty;
    update();
    if (!wasDirty) setDirty(false);
  };

  // --- Clear any selected dimension that no longer exists in the full catalog ---
  // Uses the raw (unfiltered) dimension lists, NOT the cascading-filtered ones,
  // so that an imported 4-tuple whose combination doesn't appear in
  // valid_combinations is not silently nuked.

  useEffect(() => {
    const allGamas = dims?.gamas?.map(g => g.name) ?? [];
    const allDifusores = dims?.difusores?.map(d => d.name) ?? [];
    const allLentes = dims?.lentes?.map(l => l.name) ?? [];
    const allLedTypes = dims?.led_types?.map(lt => lt.name) ?? [];

    if (gama && allGamas.length > 0 && !allGamas.includes(gama)) {
      applyAutomaticCatalogUpdate(() => setGama(''));
    }
    if (difusor && allDifusores.length > 0 && !allDifusores.includes(difusor)) {
      applyAutomaticCatalogUpdate(() => setDifusor(''));
    }
    if (lente && allLentes.length > 0 && !allLentes.includes(lente)) {
      applyAutomaticCatalogUpdate(() => setLente(''));
    }
    if (led_type && allLedTypes.length > 0 && !allLedTypes.includes(led_type)) {
      applyAutomaticCatalogUpdate(() => setLedType(''));
    }
  }, [gama, difusor, lente, led_type, dims, setGama, setDifusor, setLente, setLedType, setDirty]);

  // --- When selection changes, update the store's legacy fields ---

  useEffect(() => {
    if (ldt_id.startsWith('temp-')) return;
    if (referenceLdt && !ldt_id) {
      applyAutomaticCatalogUpdate(() => setSelectedLdt(referenceLdt));
    }
  }, [referenceLdt?.id, ldt_id, setSelectedLdt, setDirty]);

  // --- External LDT handling ---

  const clearCatalogReference = () => {
    if (!ldt_id || ldt_id.startsWith('temp-')) return;
    setSelectedLdt({
      id: '',
      manufacturer: '',
      model_family: '',
      optic_family: '',
    });
  };

  const clearExternalLdt = () => {
    setExternalLdt(null);
    setExternalError(null);
    if (externalLdt && referenceLdt) {
      setSelectedLdt(referenceLdt);
    }
  };

  const uploadExternalLdt = async (file?: File) => {
    if (!file) return;
    if (!/\.ldt$/i.test(file.name)) {
      setExternalError(t('luminaire.selectLdt'));
      return;
    }

    setUploadingExternal(true);
    setExternalError(null);
    const form = new FormData();
    form.append('file', file);
    form.append('persist', 'false');

    try {
      const response = await fetch('/api/ldt/upload', { method: 'POST', body: form });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || t('luminaire.invalidLdt'));
      }
      const ldt = data as LDTInfo;
      setExternalLdt(ldt);
      setSelectedLdt(ldt);
      setTargetFlux(ldt.flux);
      setPower(ldt.power);
      setCct(ldt.cct);
      setCri((ldt.cri === 80 || ldt.cri === 90 ? ldt.cri : 70) as 70 | 80 | 90);
    } catch (err: any) {
      setExternalError(err.message || t('luminaire.invalidLdt'));
    } finally {
      setUploadingExternal(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const activeReference = externalLdt || referenceLdt;

  // The PCB selector calculates LED power from the operating point (Vf × I).
  // Add the driver loss to show the electrical system power consistently with
  // the current shown below; the LDT reference is only used for photometry.
  // Prefer the value echoed by the backend response.  This prevents the panel
  // from mixing a new PCB result with an old driver value while an async
  // calculation is settling (the source of the 37.81 W -> 49.17 W mismatch).
  const effectiveDriverEfficiency = useMemo(() => {
    const responseEfficiency = Number(fluxDetail?.driver_eficiencia);
    return Number.isFinite(responseEfficiency) && responseEfficiency > 0
      ? responseEfficiency
      : driverEfficiency;
  }, [fluxDetail?.driver_eficiencia, driverEfficiency]);

  const electricalSystemPower = useMemo(() => {
    if (!fluxDetail) return 0;
    return fluxDetail.p_total / Math.max(effectiveDriverEfficiency, 0.01);
  }, [fluxDetail, effectiveDriverEfficiency]);

  const displayEfficiency = useMemo(() => {
    if (!fluxDetail) return 0;
    return fluxDetail.efficiency * effectiveDriverEfficiency;
  }, [fluxDetail, effectiveDriverEfficiency]);

  useEffect(() => {
    if (!gama || !difusor || !lente || !led_type || externalLdt) {
      setFluxDetail(null);
      setNoPcbWarning(false);
      setSelectedPcbRef('');
      return;
    }
    const ctrl = new AbortController();
    const tf = target_flux || 0;
    fetch('/api/ldt/flux-detail', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        gama, difusor, lente, led_type,
        cct, cri, target_flux: tf > 0 ? tf : undefined,
        i_op_ma: iOpMa && iOpMa > 0 ? iOpMa : undefined,
        lm_w_min: lmWMin && lmWMin > 0 ? lmWMin : undefined,
        driver_eficiencia: driverEfficiency,
        selected_pcb_ref: selectedPcbRef || undefined,
        t_amb_c: tAmbC,
      }),
      signal: ctrl.signal,
    })
      .then(async r => {
        if (r.status === 404) {
          setFluxDetail(null);
          setNoPcbWarning(true);
          return;
        }
        if (!r.ok) {
          setFluxDetail(null);
          setNoPcbWarning(false);
          return;
        }
        const d = await r.json();
        setFluxDetail(d);
        setNoPcbWarning(false);
        setAvailablePcbs(d.available_pcbs || []);
        if (d && d.p_total && d.p_total > 0) {
          const responseDriverEfficiency = Number(d.driver_eficiencia);
          const effectiveResponseDriverEfficiency = Number.isFinite(responseDriverEfficiency) && responseDriverEfficiency > 0
            ? responseDriverEfficiency
            : driverEfficiency;
          const systemPower = d.p_total / Math.max(effectiveResponseDriverEfficiency, 0.01);
          const nextPower = Number(systemPower.toFixed(2));
          if (Math.abs(useConfigStore.getState().power - nextPower) > 0.01) {
            applyAutomaticCatalogUpdate(() => setPower(nextPower));
          }
        }
        if (d && !selectedPcbRef && d.pcb_ref) {
          setSelectedPcbRef(d.pcb_ref);
        }
      })
      .catch(err => { if (err?.name !== 'AbortError') console.error(err); });
    return () => ctrl.abort();
  }, [gama, difusor, lente, led_type, cct, cri, target_flux, iOpMa, lmWMin, driverEfficiency, selectedPcbRef, externalLdt, referenceLdt?.id, setPower]);

  useEffect(() => {
    setSelectedPcbRef('');
  }, [gama, difusor, lente, led_type]);

  useEffect(() => {
    if (selectedPcbRef) setSelectedPcbRef('');
  }, [target_flux, iOpMa, lmWMin, driverEfficiency]);

  const formatFlux = (lm: number) => {
    if (lm >= 1000) return `${(lm / 1000).toFixed(1)}k lm`;
    return `${lm.toFixed(0)} lm`;
  };

  const formatPower = (w: number) => `${w.toFixed(0)} W`;

  const content = (
    <div className={embedded ? 'space-y-2' : 'p-4 space-y-4'}>
        {loading ? (
          <div className="text-center py-4">
            <div className="animate-spin h-5 w-5 border-2 border-[#1E1E1E] border-t-transparent rounded-full mx-auto"/>
            <p className="text-xs text-[#6a6a6a] mt-2">{t('luminaire.loadingCatalog')}</p>
          </div>
        ) : (
          <>
            {/* Pole and arm section */}
            <div className="space-y-2 rounded-lg border border-[#E8E2D8] bg-[#FCF9F5]/60 p-2.5">
              <EditableSlider
                label={t('pole.height')}
                value={height}
                min={4}
                max={40}
                step={0.01}
                unit="m"
                decimals={2}
                onChange={setHeight}
                dense={embedded}
              />
              <ArrangementPanel embedded />
            </div>

            {/* Cascading dimension selects */}
            <div className="grid grid-cols-2 gap-2">
              <label className="text-sm font-medium text-[#6A6A6A]">
                {t('luminaire.gama')}
                <select
                  value={gama}
                  onChange={e => {
                    clearExternalLdt();
                    clearCatalogReference();
                    setGama(e.target.value);
                  }}
                  className="mt-1 w-full rounded-md border border-[#E8E2D8] px-2 py-1 text-sm"
                >
                  <option value="">--</option>
                  {gamas.map(item => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
              <label className="text-sm font-medium text-[#6A6A6A]">
                {t('luminaire.difusor')}
                <select
                  value={difusor}
                  onChange={e => {
                    clearExternalLdt();
                    clearCatalogReference();
                    setDifusor(e.target.value);
                  }}
                  className="mt-1 w-full rounded-md border border-[#E8E2D8] px-2 py-1 text-sm"
                >
                  <option value="">--</option>
                  {difusores.map(item => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <label className="text-sm font-medium text-[#6A6A6A]">
                {t('luminaire.lente')}
                <select
                  value={lente}
                  onChange={e => {
                    clearExternalLdt();
                    clearCatalogReference();
                    setLente(e.target.value);
                  }}
                  className="mt-1 w-full rounded-md border border-[#E8E2D8] px-2 py-1 text-sm"
                >
                  <option value="">--</option>
                  {lentes.map(item => {
                    const eff = dims?.lentes?.find(l => l.name === item)?.eficiencia;
                    return <option key={item} value={item}>{item}{eff != null ? ` (η=${(+eff * 100).toFixed(1)}%)` : ''}</option>;
                  })}
                </select>
                {(() => {
                  const eff = dims?.lentes?.find(l => l.name === lente)?.eficiencia;
                  return eff != null ? (
                    <span className="ml-1 text-[11px] text-[#6a6a6a]">η={(+eff * 100).toFixed(1)}%</span>
                  ) : null;
                })()}
              </label>
              <label className="text-sm font-medium text-[#6A6A6A]">
                {t('luminaire.ledType')}
                <select
                  value={led_type}
                  onChange={e => {
                    clearExternalLdt();
                    clearCatalogReference();
                    setLedType(e.target.value);
                  }}
                  className="mt-1 w-full rounded-md border border-[#E8E2D8] px-2 py-1 text-sm"
                >
                  <option value="">--</option>
                  {ledTypes.map(item => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
            </div>

            <div className="grid grid-cols-4 gap-3">
              <div className="col-span-3">
                <div className="rounded-lg border border-[#E8E2D8] bg-[#FCF9F5]/70 p-2.5">
                  <label className="block truncate text-xs font-semibold text-[#6A6A6A]">
                    {t('luminaire.flux')}
                  </label>
                  <div className="mt-1.5 rounded-lg border border-[#E8E2D8] bg-[#FFFFFF] px-2.5 py-1.5 shadow-sm">
                    <div className="text-center text-sm font-semibold text-[#1E1E1E]">
                      {formatFlux(target_flux)}
                    </div>
                  </div>
                </div>
              </div>
              <label className="block text-sm font-medium text-[#6A6A6A]">
                {t('luminaire.cri')}
                <select
                  value={cri}
                  onChange={e => setCri(Number(e.target.value) as 70 | 80 | 90)}
                  disabled={Boolean(externalLdt)}
                  className="mt-1 w-full rounded-md border border-[#E8E2D8] px-2 py-1 text-sm disabled:bg-[#FFFFFF] disabled:text-[#6a6a6a]"
                >
                  <option value={70}>70</option>
                  <option value={80}>80</option>
                  <option value={90}>90</option>
                </select>
              </label>
            </div>

            {gama && difusor && lente && fluxDetail && fluxDetail.p_total > 0 && (
              <div className="rounded-md border border-[#E8E2D8] bg-[#FCF9F5] px-3 py-2 text-xs text-[#6A6A6A] flex items-center justify-between">
                <span className="font-medium">{t('luminaire.computedPower')}</span>
                <span className="font-bold text-[#1E1E1E] tabular-nums">{formatPower(electricalSystemPower)}</span>
              </div>
            )}

            {pmax !== null && fluxDetail && fluxDetail.p_total > pmax && (
              <div className="rounded-md border border-[#B42318]/25 bg-[#FDECEA] px-2 py-1 text-[11px] text-[#B42318]">
                ⚠ {t('luminaire.pmaxExceeded', { power: formatPower(fluxDetail.p_total), pmax: formatPower(pmax) })}
              </div>
            )}

            <div>
              <label className="mb-1 block text-sm font-medium text-[#6A6A6A]">
                {t('luminaire.temperature')} <span className="text-[#6a6a6a]">({cct}K)</span>
              </label>
              <div className="grid grid-cols-4 gap-1">
                {[1800, 2200, 2700, 3000, 3500, 4000, 5000, 5700].map(temp => (
                  <button
                    key={temp}
                    onClick={() => setCct(temp)}
                    disabled={Boolean(externalLdt)}
                    className={`rounded-md py-1.5 text-xs font-semibold transition-all
                      ${cct === temp
                        ? 'bg-[#1E1E1E] text-white shadow-sm'
                        : 'bg-[#FFFFFF] text-[#6A6A6A] hover:bg-[#E8E2D8]'
                      }
                      ${Boolean(externalLdt) ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    {temp}K
                  </button>
                ))}
              </div>
            </div>

            <div
              onDragOver={e => {
                e.preventDefault();
                setDragActive(true);
              }}
              onDragLeave={() => setDragActive(false)}
              onDrop={e => {
                e.preventDefault();
                setDragActive(false);
                uploadExternalLdt(e.dataTransfer.files?.[0]);
              }}
              className={`rounded-lg border p-2 text-xs transition-colors ${
                dragActive
                  ? 'border-[#1E1E1E] bg-[#1E1E1E]/20'
                  : externalLdt
                    ? 'border-[#1F7A4D]/25 bg-[#1F7A4D]/10'
                    : 'border-[#1E1E1E]/15 bg-[#1E1E1E]/6'
              } text-[#6A6A6A]`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="font-semibold text-[#6A6A6A]">
                  {externalLdt ? t('luminaire.externalLdt') : t('luminaire.referenceLdt')}
                </div>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploadingExternal}
                  className="rounded-md border border-[#E8E2D8] bg-[#FFFFFF] px-2 py-1 text-[11px] font-semibold text-[#6A6A6A] hover:bg-[#FCF9F5] disabled:opacity-50"
                >
                  {uploadingExternal ? t('actions.loading') : t('luminaire.loadLdt')}
                </button>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".ldt"
                className="sr-only"
                onChange={e => uploadExternalLdt(e.target.files?.[0])}
              />

              {activeReference && !noPcbWarning ? (
                <>
                  <div className="mt-1.5 truncate">{activeReference.luminaire_name}</div>
                  <div className={externalLdt ? 'text-[#1F7A4D]' : 'text-[#1E1E1E]'}>
                    {activeReference.power.toFixed(0)} W - {(activeReference.flux / 1000).toFixed(1)}k lm - {activeReference.efficiency.toFixed(1)} lm/W - CRI {activeReference.cri ?? 70}
                  </div>
                </>
              ) : (
                <div className="mt-1.5 text-[#6a6a6a]">{t('luminaire.noReference')}</div>
              )}

              {externalError && (
                <div className="mt-1.5 rounded-md border border-[#B42318]/25 bg-[#FDECEA] px-2 py-1 text-[#B42318]">
                  {externalError}
                </div>
              )}

              {externalLdt && (
                <button
                  type="button"
                  onClick={clearExternalLdt}
                  className="mt-1.5 rounded-md border border-[#1F7A4D]/25 bg-[#FFFFFF] px-2 py-1 text-[11px] font-semibold text-[#1F7A4D] hover:bg-[#1F7A4D]/10"
                >
                  {t('luminaire.useCatalogReference')}
                </button>
              )}
            </div>

            {noPcbWarning && !fluxDetail && (
              <div className="rounded-md border border-[#B7791F]/40 bg-[#F5EDE0] px-2 py-1.5 text-[11px] font-medium text-[#B7791F]">
                {t('luminaire.noPcbMapped')}
              </div>
            )}

            {(availablePcbs.length > 0 || fluxDetail) && (
              <div className="rounded-lg border-2 border-[#D4CEC6] bg-[#FCF9F5] p-2.5 text-[11px] space-y-2">
                <div className="flex items-center gap-2 flex-wrap">
                  {(fluxDetail?.pcb_ref || selectedPcbRef) && (
                    <span className="inline-block rounded-md bg-[#F7F4EF] text-white px-2 py-1 text-xs font-bold tracking-wide"
                      title={fluxDetail?.pcb_descripcion || ''}>
                      PCB {fluxDetail?.pcb_ref || selectedPcbRef || '?'}
                    </span>
                  )}
                  {fluxDetail?.pcb_imax_led != null && (
                    <span className="text-[10px] text-[#A09A91] font-medium">
                      I_max {(fluxDetail.pcb_imax_led * 1000).toFixed(0)} mA
                    </span>
                  )}
                  {availablePcbs.length > 1 && (
                    <select
                      value={selectedPcbRef}
                      onChange={e => setSelectedPcbRef(e.target.value)}
                      className="ml-auto rounded border border-[#D4CEC6] bg-[#FFFFFF] px-1.5 py-0.5 text-[10px] font-medium text-[#6A6A6A]"
                      title={t('luminaire.selectPcbManually')}
                    >
                      {availablePcbs.map(p => (
                        <option key={p.pcb_ref || ''} value={p.pcb_ref || ''}>
                          {p.pcb_ref} · {(p.pcb_imax_led || 0) * 1000}mA · {p.total_n_leds}LED
                        </option>
                      ))}
                    </select>
                  )}
                </div>
                {fluxDetail?.pcb_descripcion && (
                  <div className="text-[#6A6A6A] text-[11px] leading-snug whitespace-normal"
                    title={fluxDetail.pcb_descripcion}>
                    {fluxDetail.pcb_descripcion}
                  </div>
                )}
                {fluxDetail?.pcb_imax_led == null && fluxDetail && (
                  <div className="rounded border border-[#a94235]/40 bg-[#FDECEA] px-2 py-1 text-[10px] text-[#B42318]">
                    {t('luminaire.pcbNoImax')}
                  </div>
                )}
                {!fluxDetail && selectedPcbRef && (
                  <div className="rounded border border-[#B7791F]/40 bg-[#F5EDE0] px-2 py-1 text-[10px] text-[#B7791F]">
                    {t('luminaire.pcbNotCompliant')}
                  </div>
                )}
                {fluxDetail && (<>
                <div className="flex items-center gap-3 text-[11px] text-[#6A6A6A] mt-1 mb-1">
                  <span className="font-medium">{t('luminaire.iOpCalculated')}</span>
                  <span className="font-mono font-semibold text-[#1E1E1E] tabular-nums">{fluxDetail.i_op_ma.toFixed(0)} mA</span>
                  {fluxDetail.pcb_imax_led != null && (
                    <span className="text-[#6a6a6a]">(máx. {(fluxDetail.pcb_imax_led * 1000).toFixed(0)} mA)</span>
                  )}
                </div>
                <div className="space-y-1.5 pt-1 border-t border-[#E8E2D8] text-[11px]">
                  <div className="font-semibold text-[#6A6A6A] text-[10px] uppercase tracking-wide">{t('luminaire.systemPerformance')}</div>
                  <div className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5 text-[#6A6A6A]">
                    <span>Eficacia LED</span>
                    <span className="text-right font-mono tabular-nums">{fluxDetail.led_efficacy.toFixed(1)} lm/W</span>
                    <span>Factor térmico (T<sub>j</sub>)</span>
                    <span className="text-right font-mono tabular-nums">× {fluxDetail.thermal_derating.toFixed(3)}</span>
                    {fluxDetail.lente_eficiencia != null && (
                      <>
                        <span>Eficiencia óptica (lente)</span>
                        <span className="text-right font-mono tabular-nums">× {(+fluxDetail.lente_eficiencia * 100).toFixed(1)}%</span>
                      </>
                    )}
                    {fluxDetail.difusor_eficiencia != null && (
                      <>
                        <span>Eficiencia del difusor</span>
                        <span className="text-right font-mono tabular-nums">× {(+fluxDetail.difusor_eficiencia * 100).toFixed(1)}%</span>
                      </>
                    )}
                    <>
                      <span>Eficiencia del driver</span>
                      <span className="text-right font-mono tabular-nums">
                        <input type="text" inputMode="decimal" value={driverEffDraft}
                          onFocus={() => setDriverEffFocused(true)}
                          onChange={e => setDriverEffDraft(e.target.value)}
                          onBlur={() => {
                            setDriverEffFocused(false);
                            commitDriverEff(driverEffDraft);
                          }}
                          onKeyDown={e => {
                            if (e.key === 'Enter') {
                              (e.target as HTMLInputElement).blur();
                            }
                          }}
                          className="w-16 text-right bg-transparent border-b border-[#D4CEC6] focus:border-[#1E1E1E] outline-none text-inherit font-mono tabular-nums" />%
                      </span>
                    </>
                    <span className="font-semibold text-[#1E1E1E] border-t border-dotted border-[#D4CEC6] pt-0.5">Rendimiento total</span>
                    <span className="text-right font-mono tabular-nums font-semibold text-[#1E1E1E] border-t border-dotted border-[#D4CEC6] pt-0.5">{displayEfficiency.toFixed(1)} lm/W</span>
                  </div>
                  <div className="font-semibold text-[#6A6A6A] text-[10px] uppercase tracking-wide pt-1">{t('luminaire.electrical')}</div>
                  <div className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5 text-[#6A6A6A]">
                    <span>Corriente de operación (I<sub>op</sub>)</span>
                    <span className={`text-right font-mono tabular-nums ${fluxDetail.i_op_ok ? 'text-[#1F7A4D]' : 'text-[#B42318]'}`}>
                      {fluxDetail.i_op_ma.toFixed(0)} / {fluxDetail.pcb_imax_led ? (fluxDetail.pcb_imax_led * 1000).toFixed(0) : '?'} mA {fluxDetail.i_op_ok ? '✓' : '✗'}
                    </span>
                    <span>Caída de tensión (V<sub>f</sub>)</span>
                    <span className="text-right font-mono tabular-nums">{fluxDetail.v_f.toFixed(2)} V</span>
                    <span>Potencia por LED</span>
                    <span className="text-right font-mono tabular-nums">{fluxDetail.p_led.toFixed(2)} W</span>
                    <span>LEDs activos</span>
                    <span className="text-right font-mono tabular-nums">{fluxDetail.total_n_leds || '?'}</span>
                    <span>Potencia LED total</span>
                    <span className="text-right font-mono tabular-nums">{fluxDetail.p_total.toFixed(2)} W</span>
                    <span className="font-semibold text-[#1E1E1E] border-t border-dotted border-[#D4CEC6] pt-0.5">Potencia total del sistema (LED + driver)</span>
                    <span className="text-right font-mono tabular-nums font-semibold text-[#1E1E1E] border-t border-dotted border-[#D4CEC6] pt-0.5">{electricalSystemPower.toFixed(2)} W</span>
                  </div>
                  <div className="flex items-baseline justify-between pt-1.5 border-t border-[#D4CEC6]">
                    <span className="font-semibold text-[#1E1E1E] text-xs">{t('luminaire.totalLuminousFlux')}</span>
                    <span className="font-bold text-[#1E1E1E] text-sm tabular-nums">Φ = {fluxDetail.flux.toFixed(0)} lm ({formatFlux(fluxDetail.flux)})</span>
                  </div>
                  {fluxDetail.user_lm_w_min != null && (
                    <div className={`text-[10px] ${fluxDetail.lm_w_ok ? 'text-[#1F7A4D]' : 'text-[#B42318]'}`}>
                      {t('luminaire.minEfficiencyReq', { value: fluxDetail.user_lm_w_min.toFixed(0) })} {fluxDetail.lm_w_ok ? '✓ ' + t('luminaire.complies') : '✗ ' + t('luminaire.notComplies')}
                    </div>
                  )}
                </div>
              </>)}
              </div>
            )}
          </>
        )}
    </div>
  );

  if (embedded) return content;

  return (
    <div className="bg-[#FFFFFF] rounded-xl border border-[#E8E2D8] shadow-sm overflow-hidden">
      <div className="px-4 py-3 bg-[#FCF9F5] border-b border-[#E8E2D8]">
        <h3 className="font-semibold text-[#6A6A6A] flex items-center gap-2">
          <svg className="w-4 h-4 text-[#1E1E1E]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9 18h6"/><path d="M10 22h4"/><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0018 8 6 6 0 006 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 008.91 14"/>
          </svg>
          {t('luminaire.title')}
        </h3>
      </div>
      {content}
    </div>
  );
};

export default LuminairePanel;
